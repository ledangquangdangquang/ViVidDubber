from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request

from .subtitle import SubtitleBlock


class TranslationError(RuntimeError):
    pass


def _translate_blocks(
    translator,
    blocks: list[SubtitleBlock],
    source_lang: str,
    target_lang: str,
    batch_size: int,
) -> list[SubtitleBlock]:
    if not hasattr(translator, "warnings"):
        translator.warnings = []
    translated: list[SubtitleBlock] = []
    for start in range(0, len(blocks), batch_size):
        batch = blocks[start : start + batch_size]
        texts = [block.text for block in batch]
        translated_texts = translator._translate_texts(texts, source_lang, target_lang)
        if len(translated_texts) != len(batch):
            translated_texts = (translated_texts + [""] * len(batch))[: len(batch)]
            missing_idx = [
                i for i, t in enumerate(translated_texts) if not t.strip()
            ]
            if not missing_idx:
                missing_idx = list(range(len(batch)))
            for i in missing_idx:
                single = translator._translate_texts(
                    [texts[i]], source_lang, target_lang
                )
                translated_texts[i] = single[0] if single else ""
        for block, text in zip(batch, translated_texts):
            final = text.strip() if text and text.strip() else block.text
            if not text.strip():
                translator.warnings.append(
                    f"dòng {block.index} chưa dịch được, giữ bản gốc tiếng Anh"
                )
            translated.append(
                SubtitleBlock(index=block.index, start=block.start, end=block.end, text=final)
            )
    return translated


_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "th": "Thai",
    "id": "Indonesian",
}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code, code)


class _BatchTranslator:
    batch_size: int
    warnings: list[str]

    def translate_blocks(
        self,
        blocks: list[SubtitleBlock],
        source_lang: str = "en",
        target_lang: str = "vi",
        batch_size: int | None = None,
    ) -> list[SubtitleBlock]:
        if not blocks:
            return []
        self.warnings = []
        return _translate_blocks(self, blocks, source_lang, target_lang, batch_size or self.batch_size)

    def _translate_texts(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        raise NotImplementedError


class GoogleTranslator:
    def __init__(self):
        self.warnings: list[str] = []

    def translate_blocks(
        self,
        blocks: list[SubtitleBlock],
        source_lang: str = "en",
        target_lang: str = "vi",
    ) -> list[SubtitleBlock]:
        if not blocks:
            return []

        self.warnings = []
        src = "en" if source_lang in {"auto", None, ""} else source_lang
        tgt = target_lang or "vi"
        translated: list[str] = []
        failed: list[int] = []

        for i in range(0, len(blocks), 20):
            chunk = [b.text for b in blocks[i : i + 20]]
            parts = self._translate_chunk(chunk, src, tgt)
            if len(parts) != len(chunk):
                parts = []
                for text in chunk:
                    single = self._translate_chunk([text], src, tgt, retries=1)
                    parts.append(single[0] if len(single) == 1 else "")

            for block, part in zip(blocks[i : i + 20], parts):
                if part.strip():
                    translated.append(part.strip())
                else:
                    failed.append(block.index)
                    translated.append(block.text)

        for idx in failed[:10]:
            self.warnings.append(f"dòng {idx} chưa dịch được, giữ bản gốc tiếng Anh")
        if len(failed) > 10:
            self.warnings.append(
                f"…và {len(failed) - 10} dòng khác chưa dịch được (có thể do mạng hoặc Google rate-limit)"
            )

        return [
            SubtitleBlock(
                index=b.index,
                start=b.start,
                end=b.end,
                text=t,
            )
            for b, t in zip(blocks, translated)
        ]

    def _translate_chunk(self, texts: list[str], src: str, tgt: str, retries: int = 3) -> list[str]:
        joined = "\n".join(texts)
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={src}&tl={tgt}&dt=t&q={urllib.parse.quote(joined)}"
        )
        for attempt in range(retries):
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                full_trans = "".join(item[0] for item in data[0] if item and item[0])
                parsed = self._split_lines(full_trans, len(texts))
                if parsed is not None:
                    return parsed
            except Exception:
                pass
            time.sleep(2 * (attempt + 1))
        return []

    @staticmethod
    def _split_lines(full_translated: str, expected: int) -> list[str] | None:
        raw = full_translated.split("\n")
        for candidate in (raw, [x for x in raw if x.strip()]):
            if len(candidate) == expected:
                return [x.strip() for x in candidate]
        candidate = [x.strip() for x in raw if x.strip()]
        if len(candidate) > expected:
            return candidate[:expected]
        if len(candidate) < expected:
            candidate += [""] * (expected - len(candidate))
            return candidate
        return None


class EnViT5Translator(_BatchTranslator):
    """Offline translation with VietAI/envit5-translation (Transformers, GPU if available)."""
    _tokenizer = None
    _model = None
    _lock = __import__("threading").Lock()

    def __init__(self, model: str | None = None, device: str | None = None):
        self.model = model or os.environ.get("ENVIT5_MODEL", "VietAI/envit5-translation")
        self.batch_size = int(os.environ.get("ENVIT5_BATCH_SIZE", "20"))
        self.device = device or os.environ.get("ENVIT5_DEVICE", "")
        self.warnings: list[str] = []

    def _lazy_load(self):
        with self._lock:
            if self._model is None:
                try:
                    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                except ImportError as exc:
                    raise TranslationError(
                        "EnViT5 needs 'transformers' + 'torch'. Install with: "
                        "uv add transformers torch"
                    ) from exc
                os.environ.setdefault("CC", "/usr/bin/gcc")
                import torch
                self._tokenizer = AutoTokenizer.from_pretrained(self.model)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model)
                device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
                if device != "cpu":
                    self._model = self._model.to("cuda")
        return self._model, self._tokenizer

    def _translate_texts(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        model, tokenizer = self._lazy_load()
        src = source_lang.lower()
        tgt = target_lang.lower()
        encoded = tokenizer(
            [f"{src}: {t}" for t in texts],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(model.device)
        outputs = model.generate(**encoded, max_length=256)
        prefix = f"{tgt}: "
        result = []
        for o in outputs:
            text = tokenizer.decode(o, skip_special_tokens=True).strip()
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            result.append(text)
        return result


class HuggingFaceTranslator(_BatchTranslator):
    """Offline translation with tencent/Hy-MT2-1.8B via Transformers (GPU/CPU)."""
    _model = None
    _tokenizer = None
    _lock = __import__("threading").Lock()
    _HF_REPO = "tencent/Hy-MT2-1.8B"
    _DELIM = "\n-----"

    def __init__(self, model: str | None = None, device: str | None = None):
        self.repo = model or os.environ.get("HF_TRANSLATE_REPO", self._HF_REPO)
        self.batch_size = int(os.environ.get("HF_TRANSLATE_BATCH_SIZE", "20"))
        self.device = device or os.environ.get("HF_TRANSLATE_DEVICE", "")
        self.quant = os.environ.get("HF_TRANSLATE_QUANT", "4bit")
        self.warnings: list[str] = []

    def _lazy_load(self):
        with self._lock:
            if self._model is None:
                try:
                    from transformers import AutoModelForCausalLM, AutoTokenizer
                except ImportError as exc:
                    raise TranslationError(
                        "HuggingFace translate needs 'transformers' + 'torch'. "
                        "Install with: uv add transformers torch"
                    ) from exc
                os.environ.setdefault("CC", "/usr/bin/gcc")
                import torch
                self._tokenizer = AutoTokenizer.from_pretrained(self.repo)
                load_kwargs = {"dtype": torch.float16}
                if self.quant == "4bit" and torch.cuda.is_available():
                    try:
                        from transformers import BitsAndBytesConfig
                        load_kwargs = {
                            "quantization_config": BitsAndBytesConfig(
                                load_in_4bit=True,
                                bnb_4bit_compute_dtype=torch.float16,
                                bnb_4bit_use_double_quant=True,
                                bnb_4bit_quant_type="nf4",
                            ),
                        }
                    except ImportError:
                        self.warnings.append(
                            "bitsandbytes not installed; falling back to FP16 (add with `uv add bitsandbytes`)."
                        )
                self._model = AutoModelForCausalLM.from_pretrained(self.repo, **load_kwargs)
                device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
                self._model = self._model.to("cuda" if device != "cpu" else "cpu")
        return self._model, self._tokenizer

    def _translate_texts(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        model, tokenizer = self._lazy_load()
        tgt_name = _lang_name(target_lang)
        source = self._DELIM.join(texts)
        prompt = (
            f"Please accurately translate the following text into {tgt_name}. "
            "These are subtitle lines, so keep every translation short and concise — "
            "roughly the same length as the source, never longer. Avoid fluff, filler, "
            "or redundant words. You must retain the exact same number of delimiters "
            "in the translation. Strictly do not omit, escape, or translate these "
            "symbols, and pay close attention to their placement.\n\n"
            f"{source}"
        )
        messages = [{"role": "user", "content": prompt}]
        input_ids = tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        ).to(model.device)
        outputs = model.generate(
            input_ids,
            max_new_tokens=512,
            temperature=0.3,
            top_p=0.6,
            top_k=20,
            do_sample=True,
        )
        new_tokens = outputs[0][input_ids.shape[1]:]
        output_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        return [p.strip() for p in output_text.split(self._DELIM) if p.strip()]

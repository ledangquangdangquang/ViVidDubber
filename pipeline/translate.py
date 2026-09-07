from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from urllib import error, request

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


_OLLAMA_SYSTEM_PROMPT = (
    "You are a professional subtitle translator. "
    "Keep each line short and concise for subtitle timing. "
    "Output ONLY the translation text for each line, one per line. "
    "Do NOT repeat the line number in the translation text. "
    "No prefixes, no numbers, no extra text."
)


class OllamaTranslator:
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "hf.co/tencent/Hy-MT2-7B-GGUF:Q4_K_M")
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.batch_size = int(os.environ.get("OLLAMA_TRANSLATE_BATCH_SIZE", "20"))
        self.warnings: list[str] = []

    def translate_blocks(
        self,
        blocks: list[SubtitleBlock],
        source_lang: str = "en",
        target_lang: str = "vi",
        batch_size: int | None = None,
    ) -> list[SubtitleBlock]:
        self.warnings = []
        return _translate_blocks(self, blocks, source_lang, target_lang, batch_size or self.batch_size)

    def _translate_texts(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        src_name = _lang_name(source_lang)
        tgt_name = _lang_name(target_lang)
        if len(texts) == 1:
            prompt = f"Translate from {src_name} to {tgt_name}. Keep it short.\n\n{texts[0]}"
        else:
            numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
            prompt = f"Translate from {src_name} to {tgt_name}. Short.\n\n{numbered}"

        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": _OLLAMA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        return self._send_with_retry(req, expected=len(texts))

    @staticmethod
    def _parse_lines(content: str, expected: int) -> list[str]:
        numbered_re = re.compile(r"^\d+[\.\)]\s+")
        leading_digits_re = re.compile(r"^\d+\s+")
        lines = [l.strip() for l in content.split("\n") if l.strip()]

        parsed = []
        for line in lines:
            m = numbered_re.match(line)
            if m:
                t = line[m.end():].strip()
            else:
                t = leading_digits_re.sub("", line).strip()
            if t:
                parsed.append(t)

        if len(parsed) == expected:
            return parsed
        if len(parsed) > expected:
            return parsed[:expected]
        if len(parsed) < expected:
            parsed += [""] * (expected - len(parsed))
            return parsed

        parsed.clear()
        for line in lines:
            cleaned = numbered_re.sub("", line).strip()
            cleaned = leading_digits_re.sub("", cleaned).strip()
            if cleaned:
                parsed.append(cleaned)

        if len(parsed) == expected:
            return parsed
        if len(parsed) > expected:
            return parsed[:expected]
        parsed += [""] * (expected - len(parsed))
        return parsed

    def _send_with_retry(self, req: request.Request, expected: int = 1) -> list[str]:
        last_detail = ""
        for attempt in range(4):
            try:
                with request.urlopen(req, timeout=300) as response:
                    data = json.loads(response.read().decode("utf-8"))
                content = data.get("message", {}).get("content", "").strip()
                return self._parse_lines(content, expected)
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_detail = f"Ollama API error {exc.code}: {detail}"
                if exc.code != 429 or attempt == 3:
                    raise TranslationError(last_detail) from exc
                time.sleep(5 * (attempt + 1))
            except error.URLError as exc:
                if attempt == 3:
                    raise TranslationError(
                        f"Could not reach Ollama at {self.base_url}. Start it with `ollama serve`."
                    ) from exc
                time.sleep(5 * (attempt + 1))
            except Exception as exc:
                last_detail = f"Unexpected Ollama response: {exc}"
                if attempt == 3:
                    raise TranslationError(last_detail) from exc
                time.sleep(3)
        raise TranslationError(last_detail or "Ollama request failed")


class EnViT5Translator:
    """Offline translation with VietAI/envit5-translation (Transformers, GPU if available)."""
    _tokenizer = None
    _model = None
    _lock = __import__("threading").Lock()

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("ENVIT5_MODEL", "VietAI/envit5-translation")
        self.batch_size = int(os.environ.get("ENVIT5_BATCH_SIZE", "20"))
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
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
        return self._model, self._tokenizer

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


_HF_SYSTEM_PROMPT = (
    "You are a professional subtitle translator. "
    "Keep each line short and concise for subtitle timing. "
    "Output ONLY the translation text for each line, one per line. "
    "Do NOT repeat the line number in the translation text. "
    "No prefixes, no numbers, no extra text."
)


class HuggingFaceTranslator:
    """Offline translation with tencent/Hy-MT2-7B-GGUF directly from HuggingFace (Transformers)."""
    _tokenizer = None
    _model = None
    _lock = __import__("threading").Lock()
    _HF_MODEL = "tencent/Hy-MT2-7B-GGUF"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("HF_TRANSLATE_MODEL", self._HF_MODEL)
        self.batch_size = int(os.environ.get("HF_TRANSLATE_BATCH_SIZE", "20"))
        self.warnings: list[str] = []

    def _lazy_load(self):
        with self._lock:
            if self._model is None:
                try:
                    from transformers import AutoModelForCausalLM, AutoTokenizer
                except ImportError as exc:
                    raise TranslationError(
                        "HuggingFace translate needs 'transformers' + 'torch'. Install with: "
                        "uv add transformers torch"
                    ) from exc
                os.environ.setdefault("CC", "/usr/bin/gcc")
                import torch
                self._tokenizer = AutoTokenizer.from_pretrained(self.model)
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model, device_map="auto", torch_dtype=torch.float16
                )
        return self._model, self._tokenizer

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
        model, tokenizer = self._lazy_load()
        src_name = _lang_name(source_lang)
        tgt_name = _lang_name(target_lang)
        if len(texts) == 1:
            prompt = f"Translate from {src_name} to {tgt_name}. Keep it short.\n\n{texts[0]}"
        else:
            numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
            prompt = f"Translate from {src_name} to {tgt_name}. Short.\n\n{numbered}"

        messages = [
            {"role": "system", "content": _HF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        input_ids = tokenizer.apply_chat_template(messages, return_tensors="pt").to(model.device)
        output_ids = model.generate(
            input_ids, max_new_tokens=512, temperature=0.1, do_sample=False
        )
        output_text = tokenizer.decode(output_ids[0][input_ids.shape[1]:], skip_special_tokens=True).strip()
        return self._parse_lines(output_text, len(texts))

    @staticmethod
    def _parse_lines(content: str, expected: int) -> list[str]:
        numbered_re = re.compile(r"^\d+[\.\)]\s+")
        leading_digits_re = re.compile(r"^\d+\s+")
        lines = [l.strip() for l in content.split("\n") if l.strip()]

        parsed = []
        for line in lines:
            m = numbered_re.match(line)
            if m:
                t = line[m.end():].strip()
            else:
                t = leading_digits_re.sub("", line).strip()
            if t:
                parsed.append(t)

        if len(parsed) == expected:
            return parsed
        if len(parsed) > expected:
            return parsed[:expected]
        if len(parsed) < expected:
            parsed += [""] * (expected - len(parsed))
            return parsed

        parsed.clear()
        for line in lines:
            cleaned = numbered_re.sub("", line).strip()
            cleaned = leading_digits_re.sub("", cleaned).strip()
            if cleaned:
                parsed.append(cleaned)

        if len(parsed) == expected:
            return parsed
        if len(parsed) > expected:
            return parsed[:expected]
        parsed += [""] * (expected - len(parsed))
        return parsed

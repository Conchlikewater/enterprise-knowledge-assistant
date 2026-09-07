"""One-shot, deterministic query rewriting for bounded R6 retrieval."""

from __future__ import annotations

import re
from collections.abc import Sequence


class RuleBasedQueryRewriter:
    _prefixes: Sequence[re.Pattern[str]] = (
        re.compile(
            r"^(?:please\s+)?(?:can|could|would)\s+you\s+(?:please\s+)?",
            re.IGNORECASE,
        ),
        re.compile(r"^(?:please\s+)?(?:tell|show|find|explain)\s+me\s+", re.IGNORECASE),
        re.compile(
            r"^(?:请问|请告诉我|请帮我|帮我查一下|帮我找一下|能不能|可以帮我)\s*"
        ),
    )
    _replacements: Sequence[tuple[re.Pattern[str], str]] = (
        (
            re.compile(
                r"what (?:courses?|classes?) do i need (?:to take )?before",
                re.IGNORECASE,
            ),
            "prerequisite courses for",
        ),
        (
            re.compile(
                r"what prerequisites? (?:must|should) be completed before",
                re.IGNORECASE,
            ),
            "prerequisites for",
        ),
        (
            re.compile(
                r"how many credits are (?:required|needed) to (?:complete|finish)",
                re.IGNORECASE,
            ),
            "credit requirements for",
        ),
        (
            re.compile(
                r"what (?:is|are) required to graduate(?: from)?", re.IGNORECASE
            ),
            "graduation requirements for",
        ),
        (re.compile(r"需要先修哪些(?:课程|课)"), "先修课程"),
        (re.compile(r"(?:需要|要求)多少学分"), "学分要求"),
        (re.compile(r"毕业需要(?:满足)?什么(?:条件|要求)?"), "毕业要求"),
    )
    _english_stopwords = frozenset(
        {
            "a",
            "about",
            "an",
            "are",
            "can",
            "could",
            "do",
            "does",
            "for",
            "from",
            "how",
            "i",
            "in",
            "is",
            "me",
            "of",
            "please",
            "tell",
            "the",
            "this",
            "to",
            "what",
            "when",
            "which",
            "who",
            "would",
            "you",
        }
    )

    def rewrite(self, question: str) -> str | None:
        original = self._compact(question)
        if not original:
            raise ValueError("question must not be empty")
        candidate = original

        for prefix in self._prefixes:
            candidate = prefix.sub("", candidate, count=1).strip()
        for pattern, replacement in self._replacements:
            candidate = pattern.sub(replacement, candidate).strip()
        candidate = candidate.strip(" \t\r\n.!?,;:。！？，；：")

        if self._equivalent(candidate, original):
            candidate = self._keyword_fallback(original)
        if not candidate or self._equivalent(candidate, original):
            return None
        return candidate

    @staticmethod
    def _compact(question: str) -> str:
        if not isinstance(question, str):
            raise ValueError("question must be a string")
        return " ".join(question.strip().split())

    @staticmethod
    def _equivalent(first: str, second: str) -> bool:
        def normalize(value: str) -> str:
            return value.strip(" \t\r\n.!?,;:。！？，；：").casefold()

        return normalize(first) == normalize(second)

    def _keyword_fallback(self, question: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", question):
            candidate = re.sub(r"^(?:请问|请告诉我|请帮我|帮我)\s*", "", question)
            candidate = re.sub(
                r"(?:是什么|有哪些|如何|怎么|吗|呢)[？?。.]?$", "", candidate
            )
            return candidate.strip()

        tokens = re.findall(r"[A-Za-z0-9]+", question.casefold())
        keywords = [token for token in tokens if token not in self._english_stopwords]
        return " ".join(keywords) if len(keywords) >= 2 else ""

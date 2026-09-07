"""Deterministic, bounded routing for the R6 answer entry point."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.models import AnswerRoute, RouteReason, RoutingDecision


class RuleBasedQuestionRouter:
    """Route only high-confidence help and policy violations away from retrieval."""

    _greetings = frozenset(
        {
            "hello",
            "hi",
            "hey",
            "hello there",
            "good morning",
            "good afternoon",
            "good evening",
            "你好",
            "您好",
            "早上好",
            "下午好",
            "晚上好",
        }
    )
    _refusal_rules: Sequence[tuple[RouteReason, re.Pattern[str]]] = (
        (
            RouteReason.SECRET_REQUEST,
            re.compile(
                r"(?:\b(?:reveal|show|print|expose)\b.*\b(?:api[ _-]?key|secret|system prompt)\b)"
                r"|(?:打印|显示|泄露|告诉我).*(?:密钥|系统提示词|系统提示|api[ _-]?key)",
                re.IGNORECASE,
            ),
        ),
        (
            RouteReason.SCOPE_BYPASS,
            re.compile(
                r"(?:\bignore\b.*\b(?:document scope|selected documents?)\b.*\b(?:every|all|private)\b)"
                r"|(?:绕过|忽略).*(?:文档范围|所选文档|document[_ ]?ids?)"
                r"|(?:其他用户|another user(?:'s)?).*(?:文档|conversation|memory|data)"
                r"|\bmemory\b.*\banother user(?:'s)?\b",
                re.IGNORECASE,
            ),
        ),
        (
            RouteReason.EVIDENCE_BYPASS,
            re.compile(
                r"(?:\bignore\b.*\b(?:documents?|evidence|sources?)\b)"
                r"|(?:\banswer\b.*\bown knowledge\b)"
                r"|(?:\bpretend\b.*\b(?:evidence|sources?)\b.*\bsupport\b)"
                r"|(?:忽略|不参考|绕过).*(?:文档|证据|来源)"
                r"|(?:没有证据|无证据).*(?:编|捏造|回答)"
                r"|(?:假装|伪造).*(?:证据|来源)",
                re.IGNORECASE,
            ),
        ),
        (
            RouteReason.UNSUPPORTED_ACTION,
            re.compile(
                r"(?:\b(?:run|execute)\b.*\b(?:shell|command|script)\b)"
                r"|(?:\bdelete\b.*\b(?:document|file|database)s?\b)"
                r"|(?:\b(?:browse|search)\b.*\b(?:web|internet|website)\b)"
                r"|(?:\bsend\b.*\b(?:email|message)\b)"
                r"|(?:运行|执行).*(?:命令|脚本|shell)"
                r"|(?:删除|清空).*(?:文档|文件|数据库)"
                r"|(?:联网|浏览网页|搜索互联网)"
                r"|(?:发送|发).*(?:邮件|消息)",
                re.IGNORECASE,
            ),
        ),
    )
    _capability_rules: Sequence[re.Pattern[str]] = (
        re.compile(r"\bwhat can (?:you|this assistant) do\b", re.IGNORECASE),
        re.compile(r"\bwhat does this (?:assistant|system) do\b", re.IGNORECASE),
        re.compile(
            r"\bdo you remember (?:previous|past) conversations?\b", re.IGNORECASE
        ),
        re.compile(r"(?:你能做什么|有什么功能|介绍.*(?:功能|能力))"),
        re.compile(r"系统支持.*(?:文件格式|文件类型)"),
        re.compile(r"(?:记得|记住).*(?:以前|之前|历史).*(?:对话|聊天)"),
    )
    _usage_rules: Sequence[re.Pattern[str]] = (
        re.compile(
            r"\bhow (?:do|can|should) i (?:upload|select|use|ask)\b", re.IGNORECASE
        ),
        re.compile(
            r"\bhow (?:do|should) (?:i )?(?:read|use).*citations?\b", re.IGNORECASE
        ),
        re.compile(r"\bhow to (?:upload|select|use|ask)\b", re.IGNORECASE),
        re.compile(
            r"\bhelp me use (?:this |the )?(?:knowledge )?assistant\b", re.IGNORECASE
        ),
        re.compile(r"(?:如何|怎么).*(?:上传|选择文档|提问|使用)"),
        re.compile(r"citation.*(?:页码|怎么看|如何看)", re.IGNORECASE),
    )

    def route(self, question: str) -> RoutingDecision:
        normalized = self._normalize(question)
        if not normalized:
            raise ValueError("question must not be empty")

        for reason, pattern in self._refusal_rules:
            if pattern.search(normalized):
                return RoutingDecision(AnswerRoute.REFUSE, reason)

        if normalized.casefold() in self._greetings:
            return RoutingDecision(AnswerRoute.DIRECT_ANSWER, RouteReason.GREETING)
        if self._matches_any(normalized, self._capability_rules):
            return RoutingDecision(
                AnswerRoute.DIRECT_ANSWER,
                RouteReason.CAPABILITY_HELP,
            )
        if self._matches_any(normalized, self._usage_rules):
            return RoutingDecision(AnswerRoute.DIRECT_ANSWER, RouteReason.USAGE_HELP)
        return RoutingDecision(AnswerRoute.RETRIEVE, RouteReason.RETRIEVE_DEFAULT)

    @staticmethod
    def _normalize(question: str) -> str:
        if not isinstance(question, str):
            raise ValueError("question must be a string")
        compact = " ".join(question.strip().split())
        return compact.strip(" \t\r\n.!?,;:。！？，；：")

    @staticmethod
    def _matches_any(text: str, patterns: Sequence[re.Pattern[str]]) -> bool:
        return any(pattern.search(text) is not None for pattern in patterns)

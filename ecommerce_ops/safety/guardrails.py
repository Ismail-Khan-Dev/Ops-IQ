"""
Guardrails - Prompt injection protection and hallucination detection.

NOTE ON SCOPE: the prompt-injection guard in this module is a *signature
tripwire*, not a complete defense. Regex blocklists catch lazy/obvious attack
patterns but are trivially bypassed (synonyms, other languages, encoding
tricks, splitting instructions across fields, or framing attacks as legitimate
content). Treat it as one cheap layer of defense-in-depth. For any agent that
consumes truly untrusted input (e.g. public-facing chat or review text) a
second layer is required — an LLM-based injection classifier and/or stronger
input provenance — before trusting that input with tools or data.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional

logger = logging.getLogger("ecommerce_ops.safety.guardrails")


# Key placed on an LLM-analyzer result dict when untrusted input fails the
# prompt-injection tripwire. Output adapters treat its presence as a hard
# signal to quarantine the decision for human review (requires_approval=True),
# so a blocked input can never auto-execute through the rule-based fallback.
GUARDRAIL_VIOLATION_KEY = "guardrail_violation"


def guardrail_blocked(violations: List[str]) -> Dict[str, Any]:
    """Canonical "input blocked by guardrail" result.

    Returned instead of an LLM analysis when ``check_input`` fails, so the
    downstream output adapter can force the decision to HITL review with the
    offending patterns attached as evidence. Confidence is pinned to 0.0.
    """
    return {
        GUARDRAIL_VIOLATION_KEY: list(violations),
        "confidence": 0.0,
        "decision": "reject",
    }


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""

    passed: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class PromptInjectionGuard:
    """Signature tripwire for obvious prompt-injection patterns.

    This is an explicitly *limited* defense: it flags well-known attack
    phrasings (role overrides, embedded system/user tags, script/SQL idioms)
    but makes no guarantee of catching adversarial or paraphrased attempts.
    See the module docstring for the recommended second layer when handling
    untrusted input.
    """

    DANGEROUS_PATTERNS: ClassVar[List[str]] = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above\s+instructions",
        r"disregard\s+(all\s+)?previous",
        r"you\s+are\s+now\s+(?:a|an)\s+\w+",
        r"act\s+as\s+if\s+you\s+are",
        r"pretend\s+you\s+are",
        r"roleplay\s+as",
        r"system\s*:\s*you\s+are",
        r"ADMIN\s*:\s*",
        r"IMPORTANT\s*:\s*override",
        r"<\|system\|>",
        r"<\|user\|>",
        r"<\|assistant\|>",
        r"Human:\s*",
        r"Assistant:\s*",
        r"System:\s*",
        r"API_KEY",
        r"SECRET_KEY",
        r"PASSWORD",
        r"TOKEN",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
        r"INSERT\s+INTO",
        r"<script",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
    ]

    def check(self, text: str, context: Optional[str] = None) -> GuardrailResult:
        """Check text for prompt injection attempts."""
        violations = []
        warnings = []

        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Prompt injection pattern detected: {pattern}")

        # Check for unusual instruction patterns
        if "```" in text and ("system" in text.lower() or "prompt" in text.lower()):
            warnings.append("Code block with system/prompt content detected")

        # Check for role override attempts
        role_patterns = [
            r"you\s+are\s+(?:now\s+)?(?:a|an)\s+(?:assistant|bot|ai|model)",
            r"your\s+new\s+(?:role|identity|purpose)",
            r"from\s+now\s+on\s+you\s+(?:are|will|should)",
        ]
        for pattern in role_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"Role override attempt detected: {pattern}")

        passed = len(violations) == 0

        if not passed:
            logger.warning(f"Prompt injection guard failed: {violations}")

        return GuardrailResult(
            passed=passed,
            violations=violations,
            warnings=warnings,
        )


class HallucinationDetector:
    """Detect potential hallucinations in LLM responses."""

    def __init__(self, known_facts: Optional[Dict[str, Any]] = None):
        self.known_facts = known_facts or {}

    def check(
        self,
        response: str,
        context: str,
        source_data: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """Check response for potential hallucinations."""
        violations = []
        warnings = []
        details = {}

        # Check if response contains claims not supported by context
        if source_data:
            unsupported = self._check_unsupported_claims(response, source_data)
            if unsupported:
                warnings.extend([f"Potentially unsupported claim: {c}" for c in unsupported])

        # Check for fabricated numbers not in source
        response_numbers = set(re.findall(r"\b\d+\.?\d*%?\b", response))
        if source_data:
            source_text = str(source_data)
            source_numbers = set(re.findall(r"\b\d+\.?\d*%?\b", source_text))
            fabricated = response_numbers - source_numbers
            if fabricated and len(fabricated) > 3:
                warnings.append(f"Numbers in response not found in source: {fabricated}")

        # Check for overly specific claims without attribution
        specificity_patterns = [
            r"according\s+to\s+(?:the\s+)?(?:data|research|study|report)",
            r"(?:studies|research)\s+(?:show|indicate|suggest)",
            r"(\d+\.?\d*)\s+(?:percent|%)",  # Specific percentages
        ]
        for pattern in specificity_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                details["specific_claims"] = details.get("specific_claims", 0) + len(matches)

        # Check confidence level
        confidence_patterns = [
            (r"definitely|certainly|absolutely|100%", "very_high"),
            (r"likely|probably|usually", "moderate"),
            (r"might|maybe|possibly|could", "low"),
        ]
        for pattern, level in confidence_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                details["confidence_level"] = level
                break

        passed = len(violations) == 0

        return GuardrailResult(
            passed=passed,
            violations=violations,
            warnings=warnings,
            details=details,
        )

    def _check_unsupported_claims(self, response: str, source_data: Dict[str, Any]) -> List[str]:
        """Check for claims not supported by source data."""
        unsupported = []
        source_text = str(source_data).lower()
        response_sentences = re.split(r"[.!?]+", response)

        for sentence in response_sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue

            # Check if key terms from sentence appear in source
            key_terms = [word for word in sentence.split() if len(word) > 5]
            if key_terms:
                terms_in_source = sum(1 for term in key_terms if term.lower() in source_text)
                if terms_in_source == 0 and len(key_terms) > 3:
                    unsupported.append(sentence[:100])

        return unsupported[:5]  # Limit to 5


class OutputValidator:
    """Validate LLM output format and content."""

    @staticmethod
    def validate_confidence(score: float) -> GuardrailResult:
        """Validate confidence score is in valid range."""
        if not 0 <= score <= 1:
            return GuardrailResult(
                passed=False,
                violations=[f"Confidence score {score} out of range [0, 1]"],
            )
        return GuardrailResult(passed=True)

    @staticmethod
    def validate_decision(decision: str, valid_decisions: List[str]) -> GuardrailResult:
        """Validate decision is in allowed set."""
        if decision not in valid_decisions:
            return GuardrailResult(
                passed=False,
                violations=[f"Invalid decision '{decision}'. Must be one of: {valid_decisions}"],
            )
        return GuardrailResult(passed=True)

    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required: List[str]) -> GuardrailResult:
        """Validate required fields are present."""
        missing = [f for f in required if f not in data or data[f] is None]
        if missing:
            return GuardrailResult(
                passed=False,
                violations=[f"Missing required field: {f}" for f in missing],
            )
        return GuardrailResult(passed=True)

    @staticmethod
    def validate_json_structure(data: Dict[str, Any], schema: Dict[str, type]) -> GuardrailResult:
        """Validate JSON structure matches expected schema."""
        violations = []
        for key, expected_type in schema.items():
            if key not in data:
                violations.append(f"Missing key: {key}")
            elif not isinstance(data[key], expected_type):
                violations.append(
                    f"Key '{key}' has type {type(data[key])}, expected {expected_type}"
                )

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
        )


class GuardrailManager:
    """Central manager for all guardrails."""

    def __init__(self):
        self.injection_guard = PromptInjectionGuard()
        self.hallucination_detector = HallucinationDetector()
        self.output_validator = OutputValidator()

    def check_input(self, text: str, context: Optional[str] = None) -> GuardrailResult:
        """Run all input guardrails."""
        return self.injection_guard.check(text, context)

    def check_output(
        self,
        response: str,
        context: str,
        source_data: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """Run all output guardrails."""
        return self.hallucination_detector.check(response, context, source_data)

    def validate_agent_output(
        self,
        output: Dict[str, Any],
        schema: Optional[Dict[str, type]] = None,
        required_fields: Optional[List[str]] = None,
        valid_decisions: Optional[List[str]] = None,
    ) -> GuardrailResult:
        """Validate agent output against schema and constraints."""
        all_violations = []

        if required_fields:
            result = self.output_validator.validate_required_fields(output, required_fields)
            all_violations.extend(result.violations)

        if schema:
            result = self.output_validator.validate_json_structure(output, schema)
            all_violations.extend(result.violations)

        if valid_decisions and "decision" in output:
            result = self.output_validator.validate_decision(output["decision"], valid_decisions)
            all_violations.extend(result.violations)

        if "confidence" in output:
            result = self.output_validator.validate_confidence(output["confidence"])
            all_violations.extend(result.violations)

        return GuardrailResult(
            passed=len(all_violations) == 0,
            violations=all_violations,
        )


# Singleton
guardrail_manager = GuardrailManager()

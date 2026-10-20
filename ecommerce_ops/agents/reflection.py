import logging
from typing import List

from ecommerce_ops.graph.state import AgentDecision, ReflectionFeedback

logger = logging.getLogger("ecommerce_ops.agents.reflection")


class ReflectionAgent:
    async def run(self, decisions: List[AgentDecision]) -> List[ReflectionFeedback]:
        feedback: List[ReflectionFeedback] = []

        for i, d in enumerate(decisions):
            issues = []
            adjusted_conf = None

            if d.confidence_score < 0.0 or d.confidence_score > 1.0:
                issues.append("Confidence score out of [0, 1] range")
                adjusted_conf = max(0.0, min(1.0, d.confidence_score))

            if d.confidence_score > 0.95 and d.requires_approval:
                issues.append("High confidence decision sent to HITL — consider trusting the agent")
                adjusted_conf = d.confidence_score

            if d.confidence_score < 0.5 and not d.requires_approval:
                issues.append("Low confidence decision auto-approved — risk of poor outcome")

            if not d.reasoning or len(d.reasoning.strip()) < 10:
                issues.append("Reasoning is too short or empty")

            if d.action_type == "HOLD_ORDER" and d.confidence_score < 0.7:
                issues.append("Fraud hold with low confidence — may cause false positive")

            passed = len(issues) == 0
            fb = ReflectionFeedback(
                agent_id=d.agent_id,
                decision_index=i,
                passed=passed,
                issues=issues,
                adjusted_confidence=adjusted_conf,
            )
            feedback.append(fb)

        return feedback

    async def correct_decision(
        self, decision: AgentDecision, feedback: ReflectionFeedback
    ) -> AgentDecision:
        if feedback.passed:
            return decision

        corrected = decision.model_copy(deep=True)
        if feedback.adjusted_confidence is not None:
            corrected.confidence_score = feedback.adjusted_confidence

        for issue in feedback.issues:
            # Reflection may only escalate risk (auto-approved -> HITL). It must
            # NEVER flip a HITL decision to auto-approve: that would let a
            # heuristic sub-agent bypass the human-in-the-loop gate (M2).
            if "auto-approved" in issue:
                corrected.requires_approval = True

        return corrected

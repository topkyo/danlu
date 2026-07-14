"""Alchemy runner error types."""


class AlchemyJudgeProposalApplyError(RuntimeError):
    """Raised when judge_proposal_apply fails and rollback succeeds."""


class AlchemyJudgeProposalApplyHalfWriteError(RuntimeError):
    """Raised when judge_proposal_apply fails and rollback also fails; manual recovery needed."""


class AlchemyReviewApplyError(RuntimeError):
    """Raised when review_apply fails and rollback succeeds."""


class AlchemyReviewApplyHalfWriteError(RuntimeError):
    """Raised when review_apply fails and rollback also fails; manual recovery needed."""


class AlchemyLanePrimitiveReceiptError(RuntimeError):
    """Raised when lane primitive receipt persistence fails and rollback succeeds."""


class AlchemyLanePrimitiveReceiptHalfWriteError(RuntimeError):
    """Raised when lane primitive receipt persistence fails and rollback also fails."""


class AlchemyDistillApplyError(RuntimeError):
    """Raised when distill_apply fails and rollback succeeds."""


class AlchemyDistillApplyHalfWriteError(RuntimeError):
    """Raised when distill_apply fails and rollback also fails; manual recovery needed."""


class AlchemyProposeApplyReceiptError(RuntimeError):
    """Raised when propose_apply receipt-tier persistence fails and rollback succeeds."""


class AlchemyProposeApplyReceiptHalfWriteError(RuntimeError):
    """Raised when propose_apply receipt-tier rollback also fails; manual recovery needed."""

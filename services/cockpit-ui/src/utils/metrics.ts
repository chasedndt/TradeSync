/**
 * Normalizes a raw model score into a bounded strength percentage.
 * Uses tanh(x / scale) to map unbounded scores into [0, 100].
 * @param score Raw model bias score (-X to +X)
 * @param scale Dampening factor. Higher = slower saturation. Default 2.0.
 */
export function calculateBiasStrength(score: number, scale = 2.0): number {
    return Math.abs(Math.tanh(score / scale)) * 100
}

/**
 * Calculates a trade quality score (0-100) based on multiple trustworthiness factors.
 * @param params Quality inputs
 */
export function calculateQuality(params: {
    rawQuality: number; // Current backend quality (0-100)
    ageSeconds: number; // How old is the opportunity
    ttlSeconds: number; // Max age before expiry
    hasRiskVerdict: boolean; // Did we run /actions/preview
    isAllowed: boolean; // Risk verdict result
    evidenceCount: number; // Number of signals/events
    confluenceThreshold: number; // Min signals for 100% completeness
}): number {
    let score = 0;

    // 1. Freshness (40%)
    const freshnessRatio = Math.max(0, 1 - (params.ageSeconds / params.ttlSeconds));
    score += freshnessRatio * 40;

    // 2. Confluence/Evidence (30%)
    const evidenceRatio = Math.min(1, params.evidenceCount / params.confluenceThreshold);
    score += evidenceRatio * 30;

    // 3. Risk Confidence (30%)
    if (params.hasRiskVerdict) {
        score += params.isAllowed ? 30 : -50; // Heavy penalty for blocked trades
    } else {
        score += 15; // Neutral baseline if not yet previewed
    }

    // Factor in the backend's raw quality score as a discount/bonus
    const rawInertia = (params.rawQuality / 100);
    score = score * (0.8 + (rawInertia * 0.4)); // ±20% based on model confidence

    return Math.max(0, Math.min(100, score));
}

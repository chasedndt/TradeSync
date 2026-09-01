# TradeSync Quant Foundations — Book 1

Book 1 is the learning companion to TradeSync's first configurable regime rulebook. It treats mathematical understanding as an implementation gate: a formula is not ready for the dashboard merely because the code runs.

## What this book teaches

By the end, the operator should be able to:

1. read every symbol used by the first regime engine;
2. explain the difference between a raw measurement, a comparison, a normalized score, a weight, data quality, and a risk cap;
3. calculate a simple weighted score by hand;
4. explain why `tanh(z / 2)` is a design choice rather than a law of markets;
5. create and compare versioned paper-only weight sets without rewriting history;
6. identify which Year 2 mathematical topic is being used and complete the corresponding practice gate;
7. describe the database record needed to replay a score later.

## Reading order

1. [Mathematical language and notation](01_NOTATION_AND_MATH_LANGUAGE.md)
2. [Normalization, z-scores, and tanh](02_NORMALIZATION_AND_TANH.md)
3. [Weights, quality, risk caps, and experiments](03_WEIGHTING_QUALITY_AND_EXPERIMENTS.md)
4. [Year 2 module map and practice gates](04_YEAR2_MODULE_MAP_AND_PRACTICE.md)
5. [Building the quant system in public](05_BUILD_IN_PUBLIC_PRACTICE.md)
6. [Book 1 technical handover](BOOK_1_HANDOVER.md)

## Vocabulary rule

Every future mathematical document must introduce a symbol before using it. The required order is:

1. say the symbol's name;
2. say what it represents;
3. give its unit and allowed range;
4. show one numeric example;
5. only then place it inside a formula.

If the implementation uses a configurable constant, the documentation must call it a design choice and state how changing it affects the output.

## Scope and safety

This book supports education, regime research, and paper-shadow evaluation. It does not authorize a wallet, a live order, leverage, or autonomous execution. A mathematical score is evidence for a decision; it is not approval authority.

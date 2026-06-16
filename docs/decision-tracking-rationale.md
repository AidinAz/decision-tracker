# Decision tracking rationale

The project stores Decision Records directly in the repository because the relevant implementation, evaluation scripts, and supporting notes already live there. Keeping decisions next to the work makes them easier to review in pull requests and easier to recover later through Git history.

The main tradeoff is discipline. A lightweight Markdown format avoids the overhead of a separate tracking tool, but it also means contributors must remember to add or update records when important choices are made.

The expected benefit is not automated governance. The benefit is practical traceability: a reviewer can move from a decision to the code, dataset, experiment run, document, issue, or superseded decision that explains why the choice was made.

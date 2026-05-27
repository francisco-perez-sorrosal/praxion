# Eval baselines

This directory previously held committed baseline summaries for the regression eval mode.
The `regression` sub-package was **retired** in the praxion-self-eval-v1 pipeline (see
[`eval/EVAL_PLAN.md`](../../../eval/EVAL_PLAN.md) for the rationale). Baselines were keyed
by `task_slug`, but Praxion slugs are one-shot — there is no second run on the same slug to
compare against any captured baseline.

Any `.json` files remaining here are historical artifacts from before the retirement.
The broader regression-mode redesign (tier/shape-keyed envelope baselines over a Phoenix
corpus) remains deferred; see `eval/EVAL_PLAN.md` for scope.

For the current eval framework, see [`eval/README.md`](../../../eval/README.md).

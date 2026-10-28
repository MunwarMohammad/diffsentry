def summary(review):
    lines = ["## AI code review", f"Commit: `{review.head_sha}`", ""]
    if review.findings:
        lines.append(
            f"Found {len(review.findings)} potential issues. Verify suggestions before applying them."
        )
        for finding in review.findings:
            lines.append(
                f"\n- **{finding['severity'].upper()}** `{finding['file']}:{finding['line']}` — {finding['message']}"
            )
    else:
        lines.append(
            "No actionable findings in the reviewed additions. This is not a guarantee of correctness."
        )
    if review.warnings:
        lines += ["", "### Coverage limitations", *[f"- {w}" for w in review.warnings[:30]]]
    if len(review.warnings) > 30:
        lines.append(
            f"- {len(review.warnings) - 30} further coverage warnings; inspect the stored review for details."
        )
    return "\n".join(lines)

"""Report writing helpers for retrieval evaluation."""

from __future__ import annotations

from pathlib import Path

from services.evaluation_service.schemas import RetrievalReport


def write_report_files(report: RetrievalReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "retrieval_report.json"
    md_path = output_dir / "retrieval_report.md"

    json_path.write_text(report.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def render_markdown(report: RetrievalReport) -> str:
    lines: list[str] = []
    summary = report.summary
    lines.append("# Retrieval Evaluation Report")
    lines.append("")
    lines.append(f"- Generated at: {report.generated_at}")
    lines.append(f"- Base URL: `{report.base_url}`")
    lines.append(f"- Cases: `{report.cases_path}`")
    lines.append(f"- KB IDs: {', '.join(report.kb_ids) if report.kb_ids else '-'}")
    lines.append(f"- Total documents: {report.total_documents}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Case count: {summary.case_count}")
    lines.append(f"- Pass count: {summary.pass_count}")
    lines.append(f"- Fail count: {summary.fail_count}")
    lines.append(f"- Error count: {summary.error_count}")
    lines.append(f"- Precision@K: {summary.precision_at_k:.3f}")
    lines.append(f"- Recall@K: {summary.recall_at_k:.3f}")
    lines.append(f"- MRR: {summary.mrr:.3f}")
    lines.append(f"- nDCG@K: {summary.ndcg_at_k:.3f}")
    lines.append(f"- Chunk anchor hit rate: {summary.chunk_anchor_hit_rate:.3f}")
    lines.append(f"- Local priority score: {summary.local_priority_score:.3f}")
    lines.append(f"- Freshness score: {summary.freshness_score:.3f}")
    lines.append(f"- Industry relevance score: {summary.industry_relevance_score:.3f}")
    lines.append(f"- Wrong region rate: {summary.wrong_region_rate:.3f}")
    lines.append(f"- Weighted pass rate: {summary.weighted_pass_rate:.3f}")
    lines.append(f"- Hit@K: {summary.hit_at_k_rate:.3f}")
    lines.append(f"- Hit@1: {summary.hit_at_1_rate:.3f}")
    lines.append(f"- No-answer accuracy: {summary.no_answer_accuracy:.3f}")
    lines.append(f"- Golden count mismatch rate: {summary.golden_count_mismatch_rate:.3f}")
    lines.append("")

    if report.by_intent:
        lines.append("## By Intent")
        lines.append("")

    if report.by_priority:
        lines.append("## By Priority")
        lines.append("")
        lines.append("| Priority | Cases | Pass | Weighted Pass | Hit@1 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for priority, data in sorted(report.by_priority.items(), key=lambda item: item[0]):
            lines.append(
                f"| {priority} | {data.case_count} | {data.pass_count} | {data.weighted_pass_rate:.3f} | {data.hit_at_1_rate:.3f} |"
            )
        lines.append("")

    if report.by_tag:
        lines.append("## By Tag")
        lines.append("")
        lines.append("| Tag | Cases | Pass | Hit@K | Local |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for tag, data in sorted(report.by_tag.items(), key=lambda item: item[0]):
            lines.append(
                f"| {tag} | {data.case_count} | {data.pass_count} | {data.hit_at_k_rate:.3f} | {data.local_priority_score:.3f} |"
            )
        lines.append("")
        lines.append("| Intent | Cases | Pass | Precision@K | nDCG@K | Local |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for intent, data in sorted(report.by_intent.items(), key=lambda item: item[0]):
            lines.append(
                f"| {intent} | {data.case_count} | {data.pass_count} | {data.precision_at_k:.3f} | {data.ndcg_at_k:.3f} | {data.local_priority_score:.3f} |"
            )
        lines.append("")

    failed_cases = [case for case in report.cases if not case.passed][:20]
    if failed_cases:
        lines.append("## Failures")
        lines.append("")
        lines.append("| Case | Intent | Reason | Top Title | Region | Year |")
        lines.append("| --- | --- | --- | --- | --- | ---: |")
        for case in failed_cases:
            top = case.ranking[0] if case.ranking else None
            lines.append(
                f"| {case.case_id} | {case.intent or '-'} | {case.failure_reason or '-'} | {case.top_title or '-'} | {top.region if top else '-'} | {top.published_year if top else '-'} |"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"

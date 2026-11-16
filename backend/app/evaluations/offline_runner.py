"""Credential-independent CLI for existing and intelligence evaluation suites."""
import argparse
import ast
from contextlib import chdir
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',default='creatorlens_intelligence_v2')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--strict',action='store_true')
    parser.add_argument('--stream-probe',choices=['direct','timeout','history'])
    args=parser.parse_args();output=args.output.resolve() if args.output else None
    backend=Path(__file__).resolve().parents[2]
    tree=ast.parse((backend/'app/core/config.py').read_text(encoding='utf-8'))
    aliases={k.value.value for n in ast.walk(tree) if isinstance(n,ast.Call) for k in n.keywords if k.arg=='alias' and isinstance(k.value,ast.Constant) and isinstance(k.value.value,str)}
    for key in list(os.environ):
        if key in aliases or key.startswith(('GOOGLE_','OPENAI_','LANGCHAIN_','LANGSMITH_','OTEL_')):os.environ.pop(key,None)
    os.environ.update(ENVIRONMENT='test',LANGSMITH_TRACING='false',RAGAS_DO_NOT_TRACK='true',DEEPEVAL_TELEMETRY_OPT_OUT='true',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OTEL_SDK_DISABLED='true',ANONYMIZED_TELEMETRY='false')
    def guard(event,values):
        if event=='socket.connect':
            address=values[1]
            if not isinstance(address,tuple) or address[0] not in {'127.0.0.1','::1'}:raise RuntimeError('Offline evaluation blocked network access.')
        if event=='socket.getaddrinfo' and values[0] not in {'localhost','127.0.0.1','::1',None}:raise RuntimeError('Offline evaluation blocked DNS.')
    sys.addaudithook(guard)
    with tempfile.TemporaryDirectory(prefix='creatorlens-eval-') as temp,chdir(temp):
        import app.core.paths as paths
        paths.STORAGE_DIR=Path(temp)/'storage';paths.SQLITE_DB_PATH=paths.STORAGE_DIR/'creatorlens.db'
        if args.stream_probe:
            from app.evaluations.stream_probe import evaluate_stream
            print(json.dumps(evaluate_stream(args.stream_probe)));return 0
        from app.evaluations.regression_runner import run_regression
        report=run_regression(args.dataset,persist=False)
        if output:output.parent.mkdir(parents=True,exist_ok=True);output.write_text(report.model_dump_json(indent=2),encoding='utf-8')
        print(json.dumps(dict(dataset=report.dataset,version=report.dataset_version,evaluator=report.evaluator,total=report.total_cases,passed=report.passed_cases,failed=report.failed_cases,skipped=report.skipped_cases,evaluation_details=report.evaluation_details,legacy_metrics=report.aggregate_metrics if not report.evaluation_details else None,failures=[dict(case_id=c.case_id,reasons=c.failure_reasons) for c in report.cases if c.status=='FAILED']),indent=2))
        if report.evaluation_details and not args.strict:return int(not report.evaluation_details['critical_gate']['passed'])
        return int(report.failed_cases>0)

if __name__=='__main__':raise SystemExit(main())

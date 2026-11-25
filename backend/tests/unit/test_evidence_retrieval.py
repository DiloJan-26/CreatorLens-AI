"""Offline source-bound vector retrieval; expected labels/numbers are fixture-authored."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.models.rag import RetrieveRequest
from app.rag import retrieval_service as service

MODEL = "fixture-embedding-model"

@pytest.fixture
def search(monkeypatch):
    records = [dict(chunk_id=f"chunk-{n}", project_id="project", content_id=f"video-{n}",
        slot=f"content_{n}", platform="youtube", source_type="metadata" if n == 1 else "transcript",
        chunk_index=0, start_time=None, end_time=None, title=f"Video {n}", creator="Fixture",
        text="Confirmed views: 1000 and likes: 20." if n == 1 else "Dopamine participates in reward learning.",
        evidence_revision=f"revision-{n}", content_hash=f"hash-{n}", citation_label=f"Content {n} source",
        embedding_model_name=MODEL, embedding_model_version="1") for n in (1, 2)]
    calls = dict(embeddings=[], searches=[], completed=[], failed=[])
    hits = [dict(score=.8, payload=deepcopy(record)) for record in records]
    monkeypatch.setattr(service,"get_project_record",lambda _: {"id":"project"})
    monkeypatch.setattr(service,"get_settings",lambda:SimpleNamespace(embedding_model_name=MODEL,embedding_model_version="1"))
    monkeypatch.setattr(service,"get_rag_chunks",lambda *_:deepcopy(records))
    monkeypatch.setattr(service,"embed_query",lambda query: calls["embeddings"].append(query) or [.1,.2])
    monkeypatch.setattr(service,"search_project_chunks",lambda **kwargs:calls["searches"].append(kwargs) or deepcopy(hits))
    monkeypatch.setattr(service,"start_retrieval_run",lambda **_:"fixture-run")
    monkeypatch.setattr(service,"complete_retrieval_run",lambda *args,**kwargs:calls["completed"].append(kwargs))
    monkeypatch.setattr(service,"fail_retrieval_run",lambda *args,**kwargs:calls["failed"].append(kwargs))
    return records,hits,calls


def run(query="Which video has more views?", **kwargs):
    return service.retrieve_project_chunks("project",RetrieveRequest(query=query,purpose="evidence_search",**kwargs))


def test_metric_evidence_search_embeds_retrieves_and_exposes_real_diagnostics(search):
    records,hits,calls=search
    result=run(source_type="metadata")
    assert calls["embeddings"] and calls["searches"][0]["project_id"]=="project"
    assert calls["searches"][0]["source_type"]=="metadata"
    assert result.purpose=="evidence_search" and not result.structured_metadata_used
    assert len(result.results)==1 and result.results[0].chunk_id=="chunk-1"
    item=result.results[0]; details=item.match_details
    assert details.vector_match and details.rank==1
    assert details.semantic_similarity==.8 and details.matching_terms==["views"]
    assert item.score==pytest.approx(sum(details.contributions.values()),abs=1e-6)
    assert result.diagnostics.embedding_model==MODEL
    assert result.diagnostics.returned_by_slot=={"content_1":1,"content_2":0}
    assert result.retrieval_run_id=="fixture-run" and result.retrieval_latency_ms>=0
    assert result.model_dump(mode="json")["results"][0]["match_details"]["rank"]==1


def test_assistant_metric_bypass_preserved(search):
    _,_,calls=search
    result=service.retrieve_project_chunks("project",RetrieveRequest(query="Which video has more views?"))
    assert result.structured_metadata_used and result.results==[]
    assert result.diagnostics is None and not calls["embeddings"] and not calls["searches"]


def test_evidence_search_never_promotes_unmatched_stored_rows(search):
    _,hits,_=search;hits.clear()
    result=run()
    assert result.results==[] and result.diagnostics.eligible_candidates==0


@pytest.mark.parametrize("field,value",[("project_id","other-project"),("content_id","other-video"),
    ("slot","content_2"),("evidence_revision","old-revision"),("content_hash","old-hash"),
    ("text","forged evidence"),("embedding_model_name","other-model"),("embedding_model_version","2"),
    ("start_time",5),("chunk_id","orphan")])
def test_wrong_source_or_stale_vector_is_rejected(search,field,value):
    _,hits,_=search;hits[:]=[hits[0]];hits[0]["payload"][field]=value
    result=run(source_type="metadata")
    assert result.results==[]
    assert any("excluded" in note for note in result.evidence_limitations)


@pytest.mark.parametrize("score",[True,float("nan"),float("inf"),-.2,0])
def test_invalid_or_nonpositive_vector_scores_are_not_ranked(search,score):
    _,hits,_=search;hits[:]=[hits[0]];hits[0]["score"]=score
    assert run(source_type="metadata").results==[]


def test_paraphrased_query_can_retrieve_without_lexical_overlap(search):
    _,hits,_=search;hits[:]=[hits[1]]
    result=run("Pleasurable anticipation",source_type="transcript")
    assert len(result.results)==1
    assert result.results[0].match_details.keyword_overlap==0
    assert result.results[0].match_details.matching_terms==[]


def test_selected_slot_and_source_are_enforced(search):
    result=run("Explain reward learning",slot="content_2",source_type="transcript")
    assert [(r.slot,r.source_type) for r in result.results]==[("content_2","transcript")]


def test_evidence_change_during_search_is_explicit(search,monkeypatch):
    records,_,calls=search
    def embed(_):
        records[0]["text"]="Changed source"
        return [.1,.2]
    monkeypatch.setattr(service,"embed_query",embed)
    with pytest.raises(service.RetrievalValidationError,match="changed during search"):
        run(source_type="metadata")
    assert calls["failed"] and not calls["completed"]


def test_vector_failure_is_not_reported_as_successful_browse(search,monkeypatch):
    _,_,calls=search
    def fail(**_):raise RuntimeError("Synthetic vector outage")
    monkeypatch.setattr(service,"search_project_chunks",fail)
    with pytest.raises(RuntimeError,match="Synthetic vector outage"):run()
    assert calls["failed"]


def test_results_are_deterministic_for_same_query_and_snapshot(search):
    first=run("Compare reward and views")
    second=run("Compare reward and views")
    assert [c.model_dump() for c in first.results]==[c.model_dump() for c in second.results]


def test_unknown_purpose_cannot_select_generation():
    with pytest.raises(ValidationError):RetrieveRequest(query="Explain",purpose="gemini")


def test_evidence_query_bound_is_checked_before_embedding(search):
    _,_,calls=search
    with pytest.raises(service.RetrievalValidationError,match="1,000"):
        run("x"*1001)
    assert not calls["embeddings"]

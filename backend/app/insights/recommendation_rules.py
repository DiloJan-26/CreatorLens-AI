"""Fixed intervention templates. Labels establish observations, never performance causes."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RecommendationRule:
    feature: str
    category: str
    group: str
    title: str
    action: str
    rationale: str
    experiment: str
    context: str = 'any'

RULES = (
    RecommendationRule('verbal_hook_clarity','opening_hook','opening_message','Clarify the spoken opening',
        'State one main question or point before adding background detail.',
        'The validated opening clarity label supports testing a more explicit introduction.',
        'Compare the current opening with a version that states one question first; keep the rest of the explanation unchanged.'),
    RecommendationRule('topic_specificity','topic_messaging','opening_message','Name a specific topic earlier',
        'Replace a broad introductory phrase with the specific subject addressed in the cited passage.',
        'A partial or absent topic label supports clarifying the subject, not changing the subject.',
        'Record two openings for the same topic: the current wording and one that names the subject in its first sentence.'),
    RecommendationRule('curiosity_gap','opening_hook','opening_message','Make the intended question explicit',
        'If this is intended as a curiosity-led opening, state the unresolved question before its answer.',
        'The opening is classified as curiosity-led but its knowledge gap is partial or absent.',
        'Compare the current curiosity-led opening with a direct, on-topic question; retain the same answer.',context='curiosity'),
    RecommendationRule('audience_benefit','topic_messaging','opening_message','Clarify the viewer takeaway',
        'State one concrete thing the viewer can learn or try from the explanation.',
        'The assessed benefit is partial or absent; this supports a clearer statement of purpose.',
        'Test the current introduction against a version that names one takeaway before the supporting detail.'),
    RecommendationRule('audience_specificity','audience_relevance','opening_message','Clarify who the explanation is for',
        'Name the intended viewer in one short phrase without changing the topic.',
        'The audience-specificity label supports testing a more explicit intended audience.',
        'Compare the current introduction with one audience-naming phrase; let the creator choose the audience rather than infer one.'),
    RecommendationRule('problem_solution_clarity','problem_solution','narrative','Connect the stated problem to its response',
        'For this problem-led format, connect the stated problem to one explicit response before secondary detail.',
        'A problem-led opening and partial or absent problem-response clarity support this structural experiment.',
        'Keep the same material but test the sequence: stated problem, one response, then the supporting example.',context='problem'),
    RecommendationRule('spoken_cta','cta_strategy','viewer_response','Test one optional spoken next step',
        'If a follow-up fits this explanation, test one topic-related question or optional next step at the spoken ending.',
        'Supported benefit context and the assessed spoken CTA label justify an optional experiment, not a requirement to sell.',
        'Compare the current ending with one optional question about the explained topic; keep the explanation and description unchanged.',context='purpose'),
    RecommendationRule('description_cta','cta_strategy','viewer_response','Test one optional description next step',
        'If a follow-up fits this explanation, give the description one optional topic-related next step.',
        'The description CTA label supports a description-only experiment; it says nothing about a spoken CTA.',
        'Keep the video unchanged and compare two descriptions: the current text and one with a single optional follow-up question.',context='purpose'),
)

RELEVANCE = {
    'balanced': {'opening_hook':2,'topic_messaging':2,'audience_relevance':2,'problem_solution':2,'cta_strategy':1,'engagement_opportunity':1},
    'creative_quality': {'opening_hook':2,'topic_messaging':2,'audience_relevance':2,'problem_solution':2,'cta_strategy':2,'engagement_opportunity':0},
    'reach': {'opening_hook':2,'topic_messaging':2,'audience_relevance':1,'problem_solution':1,'cta_strategy':0,'engagement_opportunity':0},
    'engagement': {'opening_hook':1,'topic_messaging':1,'audience_relevance':2,'problem_solution':1,'cta_strategy':2,'engagement_opportunity':2},
}

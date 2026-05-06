# Scoring Rules

V1 scoring is deterministic and rule-based. It does not call an LLM and it does not infer user experience.

## Version

Current scoring version: `v1.0`.

Scores are stored in `match_scores` with:

- `score`: 0-100 integer.
- `explanation`: short summary of the strongest factors.
- `positive_factors_json`: factor, weight, evidence.
- `negative_factors_json`: factor, weight, evidence.
- `missing_info_json`: useful fields that were absent.

## Positive Signals

| Signal | Weight |
| --- | ---: |
| FEMA / `HSCB` | +20 |
| DHS / `HS` | +12 |
| Priority series `0089` | +10 |
| Priority series `0301`, `0343`, `1109` | +8 |
| Other priority series `0020`, `0101`, `0110`, `0300`, `0501`, `0560` | +5 |
| GS-13 | +10 |
| GS-14 / GS-15 | +12 |
| GS-12 near-target | +4 |
| Emergency management | +10 |
| Mitigation / hazard mitigation | +9 |
| Public Assistance | +8 |
| Grants management / grants | +8 |
| Disaster recovery | +8 |
| Policy/program analysis | +8 |
| Infrastructure | +6 |
| Resilience | +6 |
| Chicago | +8 |
| Midwest | +5 |
| Remote | +8 |
| Telework/hybrid | +4 |
| Supervisory | +5 |

## Negative Signals

| Signal | Weight |
| --- | ---: |
| Below GS-12 | -8 |
| Outside Midwest when not remote | -3 |
| No target signal at all | -10 |

## Missing Info

Missing info is not automatically a penalty. It is recorded so the scorecard can say what the scorer could not inspect, such as missing series, grade, location, remote status, agency, or long-form job text.

## Evidence Rule

Every positive and negative factor must cite evidence from stored structured fields or announcement text. The scorer may match terms in title, agency, summary, duties, qualifications, requirements, and evaluation factors, but it must not invent experience or assume the user's resume content.

## UI Rule

The app must show more than the number. Job detail and Scorecards expose the factor breakdown from `positive_factors_json`, `negative_factors_json`, and `missing_info_json` so the user can audit why a posting received its score.

## Relationship To Recommendations

Match scoring answers "how well does this job match the current explicit V1 rules?" Similar-job recommendations answer "what looks like jobs the user has reacted to?" Recommendation feedback can use match scores as one signal, but it must store its own explanation factors and show a separate "why suggested" view.

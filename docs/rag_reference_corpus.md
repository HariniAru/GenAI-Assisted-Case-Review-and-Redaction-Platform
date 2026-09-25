# Fictional client reference corpus for case review

Status: **draft, synthetic project material**. Northstar is a fictional client. The rules and suggested annotations below are invented for this demo; they are not real client instructions or legal advice. Have a reviewer approve the policy and example labels before treating them as authoritative.

This file is a starting corpus for a LangChain retriever. The activity descriptions remain in the application's database. Do not index this file as if it were a collection of actual customer records. The policy is the source of truth; examples illustrate its application. Index Sections 1–4 by heading or example block; Section 5 is implementation guidance, not retrieved reference material. Always include the relevant policy rules in model context, even when retrieval returns an example.

## 1. Redaction policy

Apply labels to exact substrings of the **original activity description**. Suggest a span only when its text appears verbatim in that description. A suggestion is never a saved redaction until a reviewer verifies it. Preserve the original text in storage; expanding abbreviations in a prompt must not change stored character offsets.

### PERSONAL_INFO

Protect a customer's full name, telephone number, account number, and street mailing address. Select the value itself rather than surrounding words such as `cust` or `acct`. A department name, case number, or generic role like `case mgr` is not personal information on its own. For this demo, do not infer names from initials or redact a generic relationship such as `her father`.

### CONFIDENTIAL

Protect internal settlement authority, reimbursement caps, internal pricing guidance, and instructions not to disclose those figures. Select the smallest phrase that preserves the sensitive meaning. A repair cost reported by a customer or an amount already communicated in an approved external decision would require separate review before labeling it CONFIDENTIAL.

### PRIVILEGED

For this **fictional policy**, suggest this label for a substantive instruction expressly attributed to counsel about legal position or preservation of evidence. Do not label every mention of counsel, and do not treat `No legal advice discussed` as privileged content. A reviewer determines the final label; this demo does not determine legal privilege.

### HIGHLIGHT

Mark a safety relevant vehicle symptom or incident for attention, for example unexpected acceleration, a stall, or a soft brake pedal. HIGHLIGHT is a review marker, not a concealment rule. Preserve an exact substring of the described event rather than adding a diagnosis or cause.

### Ambiguity and scope

- The policy takes precedence over a similar example. If no policy supports a label, return no suggestion and surface the uncertainty to the reviewer.
- Several separate spans may be suggested for an activity. Avoid duplicate identical spans. The seed data does not establish an overlap convention, so leave overlapping, conflicting labels for reviewer verification rather than inventing precedence.
- A note can contain both a customer-facing narrative and internal material. Apply each label to its own span; do not automatically mark the entire note.
- A `source` value of `AI` or `MANUAL` in the seed identifies how an existing redaction was entered. It is not evidence that a past reviewer approved it.

## 2. Abbreviations and client terms

Use these as exact-term lookups during preparation of model context. Expand for interpretation only; never replace the activity description used for offsets.

| Term | Meaning in this demo | Note |
| --- | --- | --- |
| cust | customer | Do not label the generic word itself. |
| veh | vehicle | Vehicle symptoms may merit HIGHLIGHT. |
| acct | account | The following account number may be PERSONAL_INFO. |
| sts | states | Preserve the customer's wording. |
| sks | asks | As used in `Cust sks c/b`. |
| c/b | callback | Not personal information alone. |
| mgr | manager | Generic role. |
| adv | advised/advises | Resolve from sentence context. |
| clld | called | Call action. |
| LM | left a message | As used in the outbound call. |
| recs | records | As used in internal notes. |
| req | request | As used in the internal note. |
| docs | documents | As used in repair documents. |
| asst | assistance | As used in `no further asst`. |
| re | regarding | Call-note shorthand. |
| Northstar Claims Dept | fictional claims department | Not PERSONAL_INFO by itself. |
| 5 Point Close | structured close-out note | Section headings may guide summaries. |

## 3. Examples against the supplied seed activities

**How to read this section:** `Existing seed annotation` means the `(text, type)` pair is already in the supplied `REDACTIONS` tuple for `ACT-1001-01`. `Proposed example` means a new synthetic illustration, **not** a database redaction or an approved client precedent. All quoted targets are exact substrings of their corresponding descriptions. Use activity UID as metadata to look up the full source text in the database; do not create new case records from these examples. These activities are useful for demos and retrieval sanity checks, but must not be scored as held-out evaluation if their examples are indexed: the retriever could simply return their expected labels. Keep scored answer keys for different activities outside the indexed corpus.

### ACT-1001-01 — unexpected acceleration and internal settlement note

Existing seed annotations:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Maria Lopez` | PERSONAL_INFO | Customer full name. |
| `(555) 014-7821` | PERSONAL_INFO | Phone number. |
| `884129` | PERSONAL_INFO | Account number. |
| `maximum settlement authorization is $4,000` | CONFIDENTIAL | Internal settlement authority. |
| `Co counsel adv team not to admit liability until investigation is complete.` | PRIVILEGED | Counsel-attributed legal instruction under the fictional policy. |
| `veh accelerated unexpectedly` | HIGHLIGHT | Safety relevant incident. |

Do not label `her father` as PERSONAL_INFO under this policy. `garage wall` is incident context, not a separate confidential figure.

### ACT-1001-02 — callback instructions

Proposed example: **no redaction suggestions**. `Northstar Claims Dept` is a department, `repair docs` are requested documents, and `no further asst` means no further assistance. Do not manufacture a phone number or personal name that is absent from this activity.

### ACT-1002-01 — voicemail

Proposed examples:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Daniel Kim` | PERSONAL_INFO | Customer full name. |
| `(555) 011-2234` | PERSONAL_INFO | Phone number. |
| `771205` | PERSONAL_INFO | Account number. |

`LM requesting c/b re veh inspection` alone has no sensitive number or safety symptom to mark.

### ACT-1002-02 — internal pricing

Proposed example:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Possible goodwill reimbursement limit is $1,500 pending mgr review.` | CONFIDENTIAL | Internal proposed cap. |
| `Do not disclose internal limit to cust.` | CONFIDENTIAL | Separate internal disclosure instruction. |

Do not assume `mgr` identifies a person.

### ACT-1003-01 — close-out note

Proposed example: `veh stalled after service` → HIGHLIGHT (reported vehicle symptom). No concealment redactions are suggested. Do not infer an accident, repair outcome, or amount from the short close-out note.

### ACT-1004-01 — stall, provisional cap, counsel instruction

Proposed examples:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Priya Shah` | PERSONAL_INFO | Customer full name. |
| `(555) 016-4402` | PERSONAL_INFO | Phone number. |
| `998231` | PERSONAL_INFO | Account number. |
| `provisional reimbursement cap of $2,200` | CONFIDENTIAL | Internal provisional cap. |
| `Counsel advises preserve inspection photos.` | PRIVILEGED | Counsel-attributed preservation instruction under the fictional policy; reviewer verifies. |
| `veh stalled near home after service` | HIGHLIGHT | Reported safety relevant symptom. |
| `brake pedal felt soft` | HIGHLIGHT | Separate safety concern. |

### ACT-1004-02 — internal pricing guidance

Proposed example:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Do not disclose internal pricing guidance to cust until final decision.` | CONFIDENTIAL | Internal disclosure instruction. |

`Mgr approved goodwill review` does not itself state a protected amount.

### ACT-1005-01 — customer mailing address

Proposed examples:

| Exact target text | Label | Reason |
| --- | --- | --- |
| `Omar Reed` | PERSONAL_INFO | Customer full name. |
| `(555) 019-8820` | PERSONAL_INFO | Phone number. |
| `42 Pinecrest Way` | PERSONAL_INFO | Street address. |
| `443210` | PERSONAL_INFO | Account number. |

`No legal advice discussed` is a negative example for PRIVILEGED; it does not contain counsel advice.

## 4. Case summary style guide

Write a short, factual case summary from the activities supplied for the case. Mention the reported vehicle issue, actions actually recorded, and current outcome or pending action. Attribute allegations to the customer (`customer reported ...`). Do not assert a root cause, liability, approval, or final resolution unless an activity says so. Keep internal caps and counsel instructions out of any customer-facing summary. If the application displays an internal-only summary, define that access policy separately; this file assumes the safer customer-facing version. Reviewer verification precedes saving `Case.ai_summary`.

## 5. Retrieval and validation notes for implementation

1. Index Sections 1–4 only. Treat policy sections, glossary entries, individual examples, and the summary guide as different document types, with metadata such as `kind`, `section`, `activity_uid`, and `status` (`seed` or `proposed`). Keep this implementation section out of the index. The relevant policy should always be available in the model context; retrieving similar examples must never replace it.
2. For the small glossary, use deterministic term matching on the activity text. Semantic search is useful for finding related examples and policy sections, but can miss short abbreviations.
3. Index this file after splitting by headings or example blocks. Do not split a target span away from its label and explanation. The full activity text comes from the current database row, not from a retrieved example.
4. For each AI-proposed span, validate `description[start:end] == proposed_text`, where `end = start + len(proposed_text)` and indexing follows Python string positions. When a target occurs more than once, require an unambiguous position before suggesting it.
5. Use ACT-1001-01, ACT-1002-02, ACT-1004-01, and ACT-1005-01 for retrieval sanity checks: inspect whether the applicable policy and useful examples are available, including the no-redaction and `No legal advice discussed` negative examples. Do not report accuracy on these activities if their labeled examples are indexed. Create a separate, non-indexed holdout set of activities and expected labels for scoring; compare model output to those answer keys only after retrieval and generation.

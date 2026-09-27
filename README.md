# 🇮🇳 Velocia

### AI-Powered Recommendation Engine for Identifying Applicable Indian Standards

> **Smart India Hackathon 2026 — Problem Statement #108**

Velocia is an intelligent recommendation engine designed to identify **applicable Indian Standards (IS)** from procurement specifications, product descriptions, technical requirements, and tender documents.

It combines **semantic search, lexical retrieval, product/category intelligence, applicability rules, and standard metadata** to retrieve and rank potentially relevant Indian Standards.

---

## 🎯 Problem Statement

| Challenge                        | Traditional Approach     | Velocia Approach                   |
| -------------------------------- | ------------------------ | ---------------------------------- |
| Different terminology            | Exact keyword matching   | Semantic similarity                |
| Typographical errors             | Poor retrieval           | Typo-tolerant processing           |
| Large number of standards        | Manual searching         | Automated ranking                  |
| Similar but irrelevant standards | Keyword overlap          | Applicability & exclusion rules    |
| Product-specific requirements    | Generic search           | Product/category intelligence      |
| Tender PDFs                      | Manual document reading  | Tender requirement extraction      |
| Understanding recommendations    | Black-box search results | Explainable recommendation signals |
| Outdated standards               | Difficult to identify    | Status & metadata filtering        |

---

## 🚀 Key Features

| Feature                    | Description                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------- |
| 🔎 Intelligent Search      | Search Indian Standards using natural-language product and specification descriptions |
| 🧠 Semantic Retrieval      | Finds standards based on contextual meaning rather than only exact keywords           |
| 🔤 BM25 Retrieval          | Provides strong lexical matching for IS numbers, titles, and technical terminology    |
| ✍️ Typo Handling           | Handles common spelling variations and input errors                                   |
| 🏷️ Product Intelligence   | Uses product, material, category, and application information                         |
| 🚫 Applicability Filtering | Removes standards that are clearly irrelevant to the given requirement                |
| 📄 Tender PDF Support      | Designed to analyze procurement/tender documents and extract relevant requirements    |
| 📚 Standard Metadata       | Uses available withdrawal, supersession, duplicate and review information             |
| 💡 Explainable Results     | Shows the signals contributing to an IS recommendation                                |
| 📊 Ranked Recommendations  | Produces an ordered list of potentially applicable standards                          |

---

# 🧠 How Velocia Works

Velocia uses a **multi-stage retrieval and recommendation pipeline**.

| Stage | Component           | Purpose                                                                |
| ----- | ------------------- | ---------------------------------------------------------------------- |
| 1     | User Input          | Accept product/specification query or tender document                  |
| 2     | Preprocessing       | Normalize and clean the input                                          |
| 3     | Query Understanding | Identify important products, materials, categories and technical terms |
| 4     | Exact Matching      | Detect direct IS-number matches                                        |
| 5     | BM25 Retrieval      | Retrieve standards with strong lexical similarity                      |
| 6     | Semantic Retrieval  | Retrieve standards using embedding similarity                          |
| 7     | Candidate Filtering | Apply product, category and applicability rules                        |
| 8     | Ranking             | Combine multiple relevance signals                                     |
| 9     | Validation          | Remove obvious mismatches and problematic records                      |
| 10    | Explanation         | Present why each standard was recommended                              |

---

# 🔬 Recommendation Signals

Velocia does not depend on a single similarity score.

| Signal              | What It Evaluates                                                  |
| ------------------- | ------------------------------------------------------------------ |
| Exact IS Match      | Whether the input directly contains an IS identifier               |
| Keyword Relevance   | Overlap between specification terminology and standard information |
| BM25 Score          | Lexical relevance between query and standard                       |
| Semantic Similarity | Contextual similarity between query and standard                   |
| Product Match       | Whether the standard applies to the identified product             |
| Material Match      | Whether the material mentioned is relevant                         |
| Category Match      | Whether the standard belongs to the relevant product/category      |
| Application Match   | Whether the intended application aligns                            |
| Rule Validation     | Whether domain-specific applicability conditions are satisfied     |
| Metadata Validation | Standard status and database consistency checks                    |

---

# 💡 Explainable Recommendations

One of Velocia's core objectives is to answer not only:

> **"Which IS code?"**

but also:

> **"Why was this IS code recommended?"**

Example:

| Recommendation Signal | Result    |
| --------------------- | --------- |
| Product Match         | ✓ Matched |
| Material Match        | ✓ Matched |
| Application Match     | ✓ Matched |
| Semantic Similarity   | ✓ High    |
| Keyword Relevance     | ✓ Strong  |
| Category Match        | ✓ Matched |
| Applicability Rules   | ✓ Passed  |
| Standard Metadata     | ✓ Valid   |

This provides procurement users with **traceable reasoning signals** instead of presenting a recommendation without context.

---

# 🏗️ System Architecture

```text
                     ┌───────────────────┐
                     │       USER        │
                     └─────────┬─────────┘
                               │
                ┌──────────────▼──────────────┐
                │        INPUT LAYER          │
                │                             │
                │ Query / Specification / PDF │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │     QUERY PROCESSING        │
                │                             │
                │ Normalization               │
                │ Typo Handling               │
                │ Product / Category Detection│
                └──────────────┬──────────────┘
                               │
             ┌─────────────────▼─────────────────┐
             │        CANDIDAT
```

# ResearchPilot 架构图生成记录

生成方式：内置 ImageGen。图为原创系统总览，采用多智能体论文常见的阶段、角色和反馈回路布局。

## 初始提示词

```text
Use case: infographic-diagram.
Asset type: a polished, publication-quality system overview figure for the GitHub README of ResearchPilot, a local-first multi-agent research preparation workbench. Generate one original raster diagram, not a screenshot, photo, code listing, or poster. Wide landscape composition, around 16:9, very high resolution, crisp legible typography on a pure white background. The visual grammar should resemble a clear modern ACL/NeurIPS multi-agent system overview: numbered stages, consistent rounded panels, restrained semantic color groups, precise arrowheads, short labels, and ample whitespace. Do not copy any existing paper's exact artwork. Use subtle teal and sage as the primary colors to match ResearchPilot's UI, with pale blue, muted lavender, and pale amber accents. Dark charcoal text, thin clean outlines; flat editorial vector-like appearance, no 3D, no gradients, no stock photos, no cute robot mascots.

Main title, verbatim: "ResearchPilot"
Subtitle, verbatim: "Local-first multi-agent research workbench"

ACCURACY IS CRITICAL. Depict exactly FIVE LLM agent roles, and distinguish the deterministic coordinator from an agent:
1 "Intent Clarifier" (small secondary text: "Goals, scope, constraints")
2 "Literature Analyst" (secondary: "Evidence and gaps")
3 "Idea Generator" (secondary: "Hypotheses and risks")
4 "Independent Reviewer" (secondary: "Accept, revise, search")
5 "Reading Planner" (secondary: "5-10 papers per idea")
All five roles share one research LLM connection; they are logically distinct roles, not five independent providers and not all parallel.

Composition:
- Top/main research lane runs clearly left to right.
- Left input card: "Researcher" with a person outline icon and short labels "Idea" and "Local folder". Arrow into agent 1 Intent Clarifier.
- Between Intent Clarifier and the four later agents, a small amber human confirmation gate labelled exactly "Confirm direction".
- A spacious central teal-framed group contains the four later agent cards in order: Literature Analyst -> Idea Generator -> Independent Reviewer -> Reading Planner.
- Above this group, a non-agent coordination band labelled "Research Coordinator", with concise smaller text "Routing | Validation | Budgets | Checkpoints". Visually show the band governs the four agent cards, rather than acting as a sixth agent. If useful, draw subtle connections from this band to cards without clutter.
- Below the central group, a small arXiv tool card labelled "arXiv search" with a document/search outline icon. Connect this tool through the coordinator with the literature evidence stage. Add one clear dashed feedback route from reviewer / reading planner back toward evidence collection, labelled "Search or revise". Make arrows unambiguous and not cross any labels.
- To the right of the central group, a second amber person / approval gate labelled "Choose and confirm". This is reached only after validated results. Then arrow to a local folder output card labelled "Project materials" containing short labels "PDFs", "Reading list", "Research README". Do not depict automatic file writing before human confirmation.
- Under the central research lane, include a concise shared service indicator "Research LLM connection" so viewers understand all five roles use this connection.
- At the bottom, a separate, independent pale-blue reading lane, visually separated from the main research workflow, labelled "Independent paper reading". Its clear flow is "Local PDF" -> "Selected text" -> "Translation connection" -> "Bilingual notes". Keep this branch clearly independent from the research LLM connection. Use browser, text selection, language, and note outline icons. Only selected text goes to translation, not the entire PDF.
- A compact local state element labelled "Local state" with smaller labels "SQLite" and "JSON checkpoints" supports the central group; it must not appear as another LLM agent. It can sit in a lower corner with a subtle link to the coordinator.

All text must be accurate, spelled correctly, and large enough to read when displayed at 1100 pixels wide in a README. Prefer short English labels exactly as specified; do not add Chinese text or long paragraphs. Integrate small restrained outline icons and numbering 1-5. Match the relative importance: research workflow most prominent, independent reading secondary. Use clear whitespace and generous margins.
Do not invent capabilities: no code generation, experiment execution, self-running scientific experiments, manuscript authoring, knowledge graph, external databases beyond arXiv, cloud deployment, Git, GitHub integration, repository operations, metrics, benchmark scores, or claims of full end-to-end success. The image is an implementation overview, not evidence that every runtime path succeeded.

```

## 定向修订提示词

```text
Edit the supplied ResearchPilot architecture diagram with only these precise arrow corrections. Preserve the overall layout, every panel, all typography, role numbering, colors, icons, title, output gate, local state, and independent reading lane.
1. Remove the extra green dashed bidirectional connection between the arXiv search tool and Research LLM connection bar. arXiv is a deterministic search tool, not an LLM role. Preserve the green dashed connections from the Research LLM connection to the five numbered agent roles.
2. Relabel the existing long blue dashed feedback route from Independent Reviewer toward arXiv search from "Search or revise" to "More evidence".
3. Add a short clear blue dashed feedback arrow from Independent Reviewer BACK TO Idea Generator, labelled "Revise", in the whitespace immediately below these cards and above the longer evidence feedback route. Keep labels and arrowheads readable without overlaps.
Do not change any other content or add any capability. Output the complete corrected wide diagram.
```


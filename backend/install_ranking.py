"""Run from anywhere; this script belongs in D:\\Velocia1."""
from pathlib import Path
import shutil
import ast

root = Path(__file__).resolve().parent
if root.name.lower() == "backend":
    root = root.parent
backend = root / 'backend'
frontend = root / 'frontend' / 'src'
main_path = backend / 'main.py'
app_path = frontend / 'App.jsx'
main = main_path.read_text(encoding='utf-8-sig')
app = app_path.read_text(encoding='utf-8-sig')
if 'from applicability import' in main:
    raise SystemExit('Ranking update already installed. No files changed.')
anchor = '    candidates = app.state.search_engine.search('
end_anchor = '    for match in matches:'
if anchor not in main or end_anchor not in main or '<strong>{result.message}</strong>' not in app:
    raise SystemExit('Files differ from expected version. No files changed; upload main.py and App.jsx.')
main = main.replace('from typo_correction import correct_query',
    'from typo_correction import correct_query\nfrom applicability import requirement_context, rank_candidates', 1)
main = main.replace(anchor, '''    context = requirement_context(corrected_requirement)
    if context["clarification"]:
        return {
            "requirement": requirement,
            "searched_requirement": corrected_requirement,
            "corrections": corrections,
            "message": "More detail is needed before recommending a cement type.",
            "clarification_question": context["clarification"],
            "standards": [],
            "search_method": "semantic_with_requirement_rules",
        }

''' + anchor, 1)
main = main.replace('top_k=3,', 'top_k=len(app.state.search_engine.standards),', 1)
main = main.replace(end_anchor, '''    matches, other_candidates = rank_candidates(matches, context)

''' + end_anchor, 1)
# Other retrieved candidates are deliberately not represented as verified references.
main = main.replace('"search_method": "semantic_with_exact_identifier_filter",',
                    '"search_method": "semantic_with_requirement_rules",')
app = app.replace('<strong>{result.message}</strong>', '''<strong>{result.message}</strong>
    {result.clarification_question && (
      <div role="status">
        <p>{result.clarification_question}</p>
        <p><small>Add the details to your requirement above and submit again.</small></p>
      </div>
    )}''', 1)
ast.parse(main)
for path, text in [(main_path, main), (app_path, app)]:
    backup = path.with_name(path.name + '.before-ranking')
    if backup.exists():
        raise SystemExit('Backup already exists; no files changed. Check prior installation.')
# Validate everything before writing. Preserve local CORS configuration.
source = Path(__file__).resolve().parent / "applicability.py"
destination = backend / "applicability.py"
if source.resolve() != destination.resolve():
    shutil.copyfile(source, destination)
for path, text in [(main_path, main), (app_path, app)]:
    shutil.copy2(path, path.with_name(path.name + '.before-ranking'))
    path.write_text(text, encoding='utf-8')
print('Updated backend/main.py and frontend/src/App.jsx. Backups saved.')
print('Restart backend and refresh frontend.')

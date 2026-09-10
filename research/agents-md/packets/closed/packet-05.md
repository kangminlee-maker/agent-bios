

===== FILE fazt/insforge-rag::AGENTS.md | stars=1 followers=7939 lang=TypeScript bytes=1611 =====

# AGENTS.md

<!-- INSFORGE:START -->
## InsForge backend

This project uses [InsForge](https://insforge.dev): an all-in-one, open-source Postgres-based backend (BaaS) that gives this app a database, authentication, file storage, edge functions, realtime, an AI model gateway, and payments through one platform.

- **Project:** **InsforgeRAG** (API base `https://4h9m57by.us-east.insforge.app`)
- **Skills:** these InsForge skills are installed for supported coding agents. Reach for them before implementing any InsForge feature instead of guessing the API:
  - `insforge`: app code with the `@insforge/sdk` client (database CRUD, auth, storage, edge functions, realtime, AI, email, and Stripe payments).
  - `insforge-cli`: backend and infrastructure via the `insforge` CLI (projects, SQL, migrations, RLS policies, storage buckets, functions, secrets, payment setup, schedules, deploys).
  - `insforge-debug`: diagnosing failures (SDK/HTTP errors, RLS denials, auth and OAuth issues) and running security or performance audits.
  - `insforge-integrations`: wiring external auth providers (Clerk, Auth0, WorkOS, Better Auth, etc.) for JWT-based RLS, or the OKX x402 payment facilitator.
  - `find-skills`: discovering additional skills on demand.
- **Credentials:** app code reads keys from `.env.local`; the CLI reads `.insforge/project.json`. Never hardcode or commit keys.

Key patterns:

- Database inserts take an array: `insert([{ ... }])`.
- Reference users with `auth.users(id)`; use `auth.uid()` in RLS policies.
- For storage uploads, persist both the returned `url` and `key`.
<!-- INSFORGE:END -->


===== FILE zeke/aeo-skill::AGENTS.md | stars=1 followers=3031 lang=None bytes=2449 =====

# AGENTS.md

Technical instructions for agents working in this repo.

## What this repo is

A single agent skill (`aeo`, Answer Engine Optimization) published for installation via `npx skills add zeke/aeo-skill`, per the [agentskills.io](https://agentskills.io/specification) spec and the [skills.sh](https://www.skills.sh) ecosystem conventions.

## Structure

```
skills/aeo/SKILL.md              — the skill entry point (frontmatter: name, description, license, metadata)
skills/aeo/references/*.md       — deep-dive reference docs linked from SKILL.md
```

This follows the convention used by `vercel-labs/agent-skills` and `anthropics/skills`: skills live at `skills/<name>/SKILL.md`, not at the repo root. The `npx skills` CLI discovers skills this way.

## Conventions

- `SKILL.md` frontmatter requires `name` and `description`. The description should include trigger phrases a user or agent might say, since that's what routes to this skill.
- Keep `SKILL.md` itself concise — it's the always-loaded context. Push depth into `references/*.md`, which get read on demand.
- No bold text in prose (per house style), but bold is fine in tables and templates where it's structural, not for emphasis.
- Don't invent new statistics or platform-specific claims. Every specific number in this skill traces to a source noted in `references/audit-methodology.md`. If adding a new claim, either cite where it came from or explicitly flag it as unverified, following the existing pattern in that file.

## Updating

AI platform behavior (crawler names, retrieval backends, citation heuristics) changes faster than most software conventions. Re-verify `references/crawler-access.md` and `references/platform-behavior.md` against current vendor documentation periodically, and note in `references/audit-methodology.md` when something has been updated.

This file should be revised whenever the skill's structure changes (new reference files added/removed, install instructions change, etc.). Keep it in sync with reality.

## Publishing

- The skill is installed via `npx skills add zeke/aeo-skill` (or a full GitHub URL). No build step, no package.json required — the CLI reads `skills/aeo/SKILL.md` directly from the repo.
- After pushing changes, the [skills.sh page](https://skills.sh/zeke/aeo-skill) picks them up automatically; no separate publish step.
- Never push directly to `main`. Use a feature branch and a PR, per standard workflow.


===== FILE antonkomarev/drema::AGENTS.md | stars=1 followers=1035 lang=Astro bytes=13995 =====

# AGENTS.md — как писать новые сказки про мышонка Мыша

Этот файл — инструкция для агента (или человека), который пишет новую сказку серии. Соблюдай канон и порядок работы с памятью.

---

## 1. Что прочитать ПЕРЕД написанием

Память мышонка лежит в трёх файлах. Прочитай все три целиком перед каждой новой сказкой:

- `src/data/characters.yaml` — друзья, с кем мышонок уже знаком (имена, как выглядят, факты).
- `src/data/things.yaml` — вещи и явления, которые он уже знает (что это, кто объяснил, факты).
- `src/data/places.yaml` — места, где он гулял (что это за место, факты).

Уже написанные сказки — в `src/content/stories/`.

Из памяти ты узнаёшь:
- **кого мышонок уже знает** — этих можно называть по имени;
- **какие факты уже прозвучали** — не противоречь им;
- **кого упомянули, но ещё не познакомили** — поле `leadsToCharacter` (например, у `spiderweb` стоит «Паук»). Это кандидаты на будущие сказки;
- **что мышонок уже понимает** — эти вещи не нужно объяснять заново;
- **где мышонок уже бывал** — знакомые места переиспользуй по их id, не заводи дубликат и не описывай заново.

---

## 2. Идентификаторы (важно для переводов)

- **id = английское название** существа, вещи или места: `grasshopper`, `spiderweb`, `spider`, `meadow`. Строчными, без пробелов (если два слова — через дефис: `water-strider`).
- id **стабилен для всех языков** и попадает в URL (`/creatures/grasshopper`, `/places/meadow`). При переводе сказок на другие языки id не меняется — меняется только человекочитаемый текст.
- **`place` в сказке — это id места** из `places.yaml` (например, `meadow`), а не русское слово. Название «Луг» для показа берётся из памяти.
- Человекочитаемые поля (`name`, `appearance`, `facts`, `whatIsIt`, `leadsToCharacter`) пишутся на языке сказки и будут переводиться.

---

## 3. Канон сказки (соблюдать всегда)

**Зачин** — каждая сказка начинается с двустишия (продолжение можно слегка менять):
> Жил да был мышонок Мышь,
> Рос он там, где шумит камыш.

**Опорная фраза** про характер — где-то в начале/середине, в стилизованном виде:
> У мышонка Мыш-мыша очень добрая душа.

**Совы — опасность.** Рано утром (туман над камышом) и поздно вечером (закат) над норкой бесшумно пролетают совы. В эти часы мышонок прячется. Приключения — только днём, когда совы скрылись.

Упоминать сов прямо в сказке **необязательно**, и не нужно непременно показывать их и утром, и вечером — появление сов утром и/или вечером опционально. Обязателен лишь сам канон: приключения идут днём, а время суток согласовано (вышел, когда совы скрылись; вернулся домой к закату).

### Структура (по порядку)

1. **Утро.** Коротко: проснулся, сладко потянулся; какая сегодня погода (каждый раз своя); у норки растут колокольчики — умылся, попил водички, почистил зубки; зарядка; завтрак. Цель — показать ребёнку ценность ежедневных ритуалов.
2. **Куда пошёл гулять.** Назвать место (луг, лес, поле, озеро, болото, горка…) и дать почувствовать, что мышонок там немного погулял — до или после встречи, чтобы день шёл своим чередом, а не обрывался сразу.
3. **Загадка.** Мышонок видит незнакомца и НЕ знает, кто это. Описываем, **как тот выглядит** (через сравнения, глазами мышонка). Мышонок гадает.
4. **Мышонок представляется сам полным именем:** «Привет! Я Мыш-мышь. А тебя как зовут?»
5. **Знакомство** — новый герой называет себя (тут читатель узнаёт, кто это).
6. **Помощь** — мышонок замечает беду и помогает.
7. **Расспросы** — после помощи мышонок спрашивает: чем обычно занимаешься? как живёшь? Герой рассказывает о своей настоящей жизни (познавательная часть).
8. **Вечер.** Коротко, без пересказа всего дня: наступает вечер, мышонок уже дома; вечерние ритуалы (умылся, почистил зубки); ложится спать, зная, как важно выспаться и набраться сил. Мостик: «а завтра его ждала новая встреча».

### Имя героя

- Полное имя героя — **Мыш-мышь**. Короткая форма (как зовут друзья и как звучит в зачине) — **Мышь**.
- **Зачин всегда** начинается строкой «Жил да был мышонок Мышь» (короткая форма, она рифмуется с «камыш»).
- В тексте сказки (нарратив) героя называем **Мыш-мышь**.
- Когда герой знакомится с новым существом, он представляется полным именем: «Я Мыш-мышь». Уже знакомые друзья в диалогах зовут его коротко — Мышь.
- Опорная фраза (рефрен) остаётся неизменной: «У мышонка Мыш-мыша очень добрая душа».

### Имена существ, вещей и мест

Существ, вещи и места называем в **базовой форме, без уменьшительно-ласкательных**: Паук (не Паучок), Мышь (не Мышка), Осёл (не Ослик), Жук (не Жучок), Лягушка (не Лягушонок), Паутина (не паутинка), Луг (не Лужок). Это касается и текста сказки, и полей `name` / `leadsToCharacter` в памяти.

**Описание самой вещи — тоже строгое:** паутину описываем как «нити» (не «ниточки»), «сеть» (не «сеточка»). Имя вещи и то, как её объясняют, держим без диминутивов.

**Тёплые слова в нарративе сохраняем** — солнышко, ветерок, зёрнышки, водичка, зубки, лапки, постелька. Это интонация для самых маленьких в утренних/вечерних ритуалах и описаниях, а не названия объектов. Запрет на диминутивы — только для имён существ/вещей и описания самих вещей.

### Два правила про «новизну мира»

- **Не называть незнакомцев заранее.** Нельзя упоминать по имени существ, с кем мышонок ещё не знаком. Пока не знакомы — только абстрактно: «кто-то порхал над цветами», «мелькнули яркие крылышки». Растения, облака, солнце, ветер, камыш, цветы — называть можно. Героев из прошлых сказок — тоже можно.
- **Незнакомые предметы объясняет друг.** Если встречается незнакомая вещь (паутина, мёд, эхо…), мышонок не знает, что это, и новый друг ему объясняет. В объяснении друг может мельком назвать существо, с которым мышонок ещё не знаком (так Кузнечик назвал паука) — это разрешённое предвестие будущей сказки. Запиши такое существо в `leadsToCharacter` у соответствующей вещи.

---

## 4. Что сделать ПОСЛЕ написания (обновить память)

1. **Сказка** → новый файл `src/content/stories/NNN-meeting-<id-героя>.md` (трёхзначный номер + `meeting-` + английский id героя, например `002-meeting-water-strider.md`):
   ```yaml
   ---
   number: 2
   title: "Знакомство с Водомеркой"
   place: "lake"                    # id места из places.yaml
   characters: ["water-strider"]   # id новых друзей
   things: []                       # id новых вещей
   date: 2026-06-29
   ---
   (текст сказки)
   ```
2. **Новый друг** → запись в `src/data/characters.yaml` (ключ = английский id):
   ```yaml
   water-strider:
     name: Водомерка
     emoji: 🦟
     appearance: "…как выглядит глазами мышонка…"
     home: на глади озера
     metInStory: 2
     facts:
       - "…"
   ```
3. **Новая вещь** → запись в `src/data/things.yaml` (с `learnedFrom`, `firstInStory`, при необходимости `leadsToCharacter`).
4. **Новое место** → если мышонок пришёл туда, где ещё не был, добавь запись в `src/data/places.yaml` (ключ = английский id, поля `name`, `emoji`, `whatIsIt`, `facts`). Если место уже знакомо — просто сошлись на существующий id в поле `place`.
   ```yaml
   lake:
     name: Озеро
     emoji: 🌊
     whatIsIt: большая тихая вода, по которой можно скользить
     facts:
       - "…"
   ```
5. Перечисли новых героев и вещи в сказке по их **id**, а место укажи id в поле `place`.
6. Если познакомили кого-то, кто раньше был в `leadsToCharacter`, — он теперь полноценный друг; поле-предвестие можно убрать.

---

## 5. Технические правила

- **YAML-кавычки:** если в строке есть `:`, `#` или кавычки — бери её в "двойные кавычки".
- **Проверка:** перед коммитом запусти `pnpm build` (или `docker compose up --build`). Память валидируется по схеме — пропущенное или неверное поле остановит сборку с точечной ошибкой (например, `Память (друзья) → «water-strider»: metInStory Required`). Это нормально: исправь поле и собери снова.
- Сайт и память — один источник: достаточно обновить YAML и добавить файл сказки, страницы и перелинковка соберутся сами.

---

## 6. Чек-лист перед сдачей сказки

- [ ] Зачин-двустишие на месте.
- [ ] Есть фраза «у мышонка Мыш-мыша очень добрая душа».
- [ ] Время суток согласовано (приключения — днём); совы упомянуты опционально.
- [ ] Утренние ритуалы → прогулка с названием места → загадка → знакомство → помощь → расспросы → вечер со сном.
- [ ] Не названы существа, с кем мышонок ещё не знаком.
- [ ] Незнакомые предметы объяснены другом.
- [ ] Память обновлена (YAML друзей/вещей/мест + файл сказки), id на английском.
- [ ] Поле `place` — это id места из `places.yaml` (новое место заведено, знакомое переиспользовано).
- [ ] `pnpm build` проходит без ошибок.


===== FILE tw93/static::AGENTS.md | stars=1 followers=12312 lang=JavaScript bytes=1786 =====

# static Agent Guide

## Project

This repository hosts static files used by Tw93 projects, including app downloads, images, appcast files, and web assets.

Deploy surface: pushing `main` is production. Vercel publishes every push immediately, and these URLs are referenced live by other projects; there is no staging.

## Repository Map

- `app/` - downloadable app artifacts.
- `img/` - shared images and icons.
- `miaoyan/` - MiaoYan media assets.
- `mole/` - Mole update feed and related assets.
- `pake/` - Pake screenshots, icons, and media.
- `pic/` - miscellaneous images and documents.
- `uPic/` - uPic static assets.
- `video/` - hosted video assets.
- `clash/` - Clash configuration and related public files.
- `index.html` - simple static index.
- `vercel.json` - deployment routing/configuration.

## Working Rules

- Treat files here as public CDN assets.
- Do not delete or rename assets unless the referencing project is updated at the same time.
- Preserve stable URLs for downloads, appcasts, screenshots, and README assets.
- Treat `clash/` configs as public files; avoid adding private endpoints, tokens, or machine-specific values.
- Avoid committing local editor files or generated temporary artifacts.

## Verification

- Asset replacement: confirm the target path is intentional and referenced by the owning project.
- Appcast changes: validate XML structure and confirm download URLs are reachable.
- Clash config changes: validate syntax and scan for private endpoints or secrets before committing.
- HTML changes: open or build-check the affected static page when possible.
- Documentation-only changes: check links and paths.

## GitHub Operations

- Use `gh` for issue and PR inspection.
- Do not post public comments unless the maintainer explicitly asks.


===== FILE dfinke/agent-readable-repo-lab::AGENTS.md | stars=1 followers=1492 lang=PowerShell bytes=1982 =====

# AGENTS.md

Instructions for AI coding agents working in this repo.

## Project Purpose

This repository tests whether agents can understand an open source project by following progressively richer breadcrumbs. The implementation project is `ToyReport`, a tiny PowerShell module that turns a sales CSV into an HTML report.

## Main Command

Use the existing command:

```powershell
Invoke-ToyReport -InputCsvPath ./examples/sales.csv -OutputHtmlPath ./report.html
```

Do not invent new public APIs unless the task explicitly requires one.

## Run Examples

From the repository root:

```powershell
pwsh -NoProfile -File ./examples/basic.ps1
pwsh -NoProfile -File ./examples/export-report.ps1
pwsh -NoProfile -File ./examples/agent-task.ps1
```

## Run Tests

The tests use Pester.

```powershell
pwsh -NoProfile -Command "Invoke-Pester -Path ./tests"
```

If Pester is not installed:

```powershell
pwsh -NoProfile -Command "Install-Module Pester -Scope CurrentUser -Force -SkipPublisherCheck"
```

## Important Paths

- `README.md`: Short human-facing overview.
- `llms.txt`: Agent-readable map and verification route.
- `docs/`: GitHub Pages site and expanded documentation.
- `src/ToyReport.psm1`: PowerShell module implementation.
- `examples/`: Runnable examples using sample data.
- `tests/`: Pester tests for expected behavior.
- `prompts/`: Prompts for evaluating agent discovery.

## Modification Rules

- Read `llms.txt` and relevant examples before changing implementation.
- Prefer extending examples before changing `src/ToyReport.psm1`.
- Add or update tests when behavior changes.
- Keep the project cross-platform: use `pwsh`, `Join-Path`, and .NET APIs that work on Windows, macOS, and Linux.
- Do not use Excel, COM automation, Windows-only paths, or machine-specific assumptions.
- Keep `Invoke-ToyReport` simple, readable, and dependency-free.
- Preserve the progressive-disclosure experiment: breadcrumbs should point agents toward docs, examples, and tests.


===== FILE banteg/snail::AGENTS.md | stars=1 followers=2972 lang=C bytes=559 =====

for git, use conventional commits style

When running anything Python-related, prefer `uv`:
- run scripts: `uv run script.py` (or `uv run script_name` if it's an entrypoint)
- run tests: `uv run pytest`
- run tools: `uv run ruff`, `uv run ty`
- add/remove deps: `uv add`, `uv remove`

When using `gh`:
- PR title must be in the form of a conventional commit
- When asked to merge, use `gh pr merge --squash <pr>`
- To avoid escaping issues, write the PR description to a file and use:
  - `gh pr create --body-file <file>`
  - `gh pr edit --body-file <file>`


===== FILE djnavarro/emaxnls::AGENTS.md | stars=1 followers=1185 lang=R bytes=9730 =====

# emaxnls — Project Memory

This file is loaded automatically by Posit Assistant at the start of every conversation.
It captures project context so the assistant can help without needing repeated explanation.

---

## What this package does

`emaxnls` implements Emax dose-response regression models for pharmacokinetic/pharmacodynamic
analysis. It supports:

- **Continuous responses** via nonlinear least squares (`emax_nls()`)
- **Binary responses** via logistic Emax regression (`emax_logistic()`)
- **Stepwise covariate modelling** (SCM) via `emax_scm_forward()` / `emax_scm_backward()`
- **Simulation** from fitted models (`simulate()`)

The Emax model has parameters `E0` (baseline), `Emax` (maximum effect), `EC50` (half-maximal
concentration), and optionally `Hill` (sigmoidal shape). Parameters `EC50` and `Hill` are
estimated on the log scale internally (`logEC50`, `logHill`), with back-transformation available
via `back_transform = TRUE`.

The package is on CRAN at version 0.1.1; the development version is 0.1.1.9000.
It also integrates with the pre-CRAN **erplots** package (GitHub: `djnavarro/erplots`) for
ggplot2-based visualisation of Emax models (see `erplots::er_plot_add_model()` etc.).  
Package website: https://emaxnls.djnavarro.net/

---

## Package structure

```
R/                      # Source code
  api.R                 # Main user-facing functions (emax_nls, emax_logistic, options, init)
  emaxnls-class.R       # S3 class construction for emaxnls
  emaxnls-methods.R     # S3 methods: coef, vcov, confint, residuals, fitted, predict, etc.
  emaxnls-printing.R    # print() and summary()
  emaxnls-init.R        # Starting value and bounds generation
  emaxnls-options.R     # Option configuration
  emaxnls-predict.R     # Predictions with optional SE
  emaxnls-simulate.R    # Monte Carlo simulation from fitted models
  emaxnls-scm.R         # Stepwise covariate modelling
  emaxnls-update.R      # emax_add_term() / emax_remove_term()
  emaxlogistic-*.R      # Binary response equivalents of each of the above
  er-methods.R          # erplots interface: er_predict/er_simulate/er_summary + .onLoad()
  data.R                # emax_df dataset documentation
  utils-*.R             # Internal helpers: validators, mappers, safe wrappers

tests/testthat/         # Test suite (testthat edition 3)
  helper-platform.R     # Shared helpers: skip_if_not_converged(), test_nls_opts(), etc.
  test-*.R              # One file per feature area

vignettes/articles/     # Four long-form articles
  fitting-emax-models.Rmd
  fitting-logistic-emax-models.Rmd
  simulating-from-emax-models.Rmd
  stepwise-covariate-modelling.Rmd

dev/                    # Developer-focused notes (not part of the package)
  # Informal notes to track ongoing investigations, platform quirks, etc.
```

---

## Key classes

| Class | Description |
|-------|-------------|
| `emaxnls` | Fitted continuous Emax model |
| `emaxlogistic` | Fitted binary/logistic Emax model |
| `emaxnls_null` | Returned when model fails to converge (graceful failure) |

Models expose the standard S3 interface: `coef()`, `vcov()`, `confint()`, `residuals()`,
`fitted()`, `predict()`, `simulate()`, `logLik()`, `AIC()`, `BIC()`, `anova()`, `print()`,
`summary()`, `sigma()`, `deviance()`, `nobs()`, `df.residual()`.

When erplots is loaded, models also respond to `erplots::er_predict()`,
`erplots::er_simulate()`, and `erplots::er_summary()` (registered lazily via `.onLoad()` in
`R/er-methods.R`; no hard dependency on erplots).

**`sim_resp` addition (feature/er-simulate-sim-resp branch, not yet merged).**
erplots' `er_vpc_plot()` used to require a bespoke, model-package-specific simulation
helper rather than going through the shared `er_predict()`/`er_simulate()`/`er_summary()`
interface -- a design gap on the erplots side, closed by widening erplots' `er_simulate()`
contract additively: a method may now return an optional `sim_resp` column (a full
response-scale draw, including observation-level noise) alongside the existing `fit_resp`
(expected response under parameter uncertainty only). `er_simulate.emaxnls()` now computes
`sim_resp` too, reusing the same noise models already used by
`simulate.emaxnls()`/`simulate.emaxlogistic()` (`.emax_resample()`/
`.emax_logistic_resample()`): `Normal(fit_resp, sigma(model))` for `emaxnls`,
`Bernoulli(fit_resp)` for `emaxlogistic`. See erplots' `?er_model_interface` for the
updated contract this satisfies.

---

## Naming conventions

- **Public API functions**: no prefix, `snake_case` (e.g., `emax_nls()`, `emax_add_term()`)
- **Internal/private functions**: dot prefix (e.g., `.emax_nls()`, `.validate_formula()`)
- **Safe wrappers**: `.safe_fn()`, `.quiet_fn()`, `.nls_safe()`, `.nls_lm_safe()`
- **Assertions/validators**: `.assert()`, `.validate_*()`
- **File naming**: `{class}-{concern}.R` for class-specific files (e.g., `emaxnls-methods.R`),
  `utils-{concern}.R` for shared utilities

---

## Optimization algorithms

Three algorithms are available via `optim_method`:

| Value | Algorithm | Notes |
|-------|-----------|-------|
| `"gauss"` (default) | Gauss-Newton | Delegates to `nls()` |
| `"port"` | nl2sol (Port library) | Delegates to `nls(..., algorithm = "port")`, supports bounds |
| `"levenberg"` | Levenberg-Marquardt | Delegates to `minpack.lm::nls.lm()` |

All fittings support a `max_time` argument (in seconds) to prevent hangs. The default in
tests is 10 seconds via `test_nls_opts()`.

---

## Testing conventions

- Framework: testthat 3.0.0 edition
- Test helpers live in `tests/testthat/helper-platform.R`
- Use `test_nls_opts()` / `test_logistic_opts()` when fitting models inside tests — these
  set `max_time = 10` to avoid hangs
- Use `skip_if_not_converged(mod)` to skip a test block when a model fails to converge
  (acceptable on some platforms/compilers)
- Platform helpers: `is_clang()`, `is_gcc15()`, `gcc_version()`, `mvtnorm_usable()`
- `mvtnorm` (used for simultaneous confidence intervals) has runtime failures on some
  platforms; the package degrades gracefully when it is unavailable
- `test-er-methods.R` gates all tests on `skip_if_not_installed("erplots")` — no erplots
  needed for the base test suite to pass

---

## Key dependencies

| Package | Role |
|---------|------|
| `minpack.lm` | Levenberg-Marquardt optimiser |
| `Deriv` | Symbolic differentiation for gradient computation |
| `mvtnorm` | Multivariate normal sampling for simultaneous CIs |
| `rlang` | Error/condition signalling |
| `stats`, `utils` | Base R (NLS, formula handling, etc.) |
| `tibble` | Suggested (optional); package works without it |
| `erplots` | Suggested (optional, pre-CRAN); enables `er_plot` visualisation pipeline |

---

## Data

`emax_df` is a built-in synthetic dataset with 400 observations used in examples and tests:
- Continuous and binary response variables
- Multiple exposure metrics
- Continuous, binary, and categorical covariates
- Dose groups: 0, 100, 200, 300

---

## Formula interface

```r
# Structural model: response ~ exposure
emax_nls(response ~ exposure, data = df)

# Covariate model: list of two-sided formulas, one per parameter
emax_nls(
  response ~ exposure,
  covariate_model = list(
    E0     ~ cov1 + cov2,
    Emax   ~ cov1,
    logEC50 ~ cov1
  ),
  data = df
)
```

---

## Development workflow

- Documentation generated with roxygen2 (version 8.0.0, markdown enabled)
- CI/CD via GitHub Actions: R CMD check, test coverage (Codecov), pkgdown build, rhub
- Spell checking via `spelling` (custom words in `inst/WORDLIST`)
- README generated from `README.Rmd`
- **Use US English spelling** in all code comments, roxygen documentation, vignettes, and
  other prose (e.g. "behavior" not "behaviour", "color" not "colour", "modeling" not
  "modelling")
- **Code style by context**: the package itself has minimal dependencies, so `@examples`
  blocks and any other code embedded in roxygen documentation must use base R only — no
  tidyverse. Articles in `vignettes/articles/` are website-only and are not part of the
  package; tidyverse style is preferred there.

### Common commands

| Task | Command |
|------|---------|
| Regenerate documentation | `devtools::document()` |
| Run test suite | `devtools::test()` |
| Build pkgdown site | `pkgdown::build_site()` |

### Generated files — do not edit directly

`NAMESPACE` and all files under `man/` are generated by roxygen2. Never edit them directly;
edit the roxygen source in `R/` and regenerate with `devtools::document()`.

---

## Assistant preferences

### Autonomy

- For **large or structural changes** (touching multiple files, renaming public functions,
  reorganising classes), propose a plan and ask for approval before editing files. Act
  directly on small, well-scoped changes.
- When making non-trivial changes, **explain the reasoning** only when the decision is
  non-obvious or involves a tradeoff. Skip explanation for routine fixes.
- After making code changes, **run `devtools::test()`** to verify nothing is broken.
- When a change warrants a `NEWS.md` entry, **suggest what to add** but do not write it
  — leave changelog management to the developer.

### Dependencies

- The package has a minimal-dependency philosophy. **Ask before adding any new dependency**
  to either `Imports` or `Suggests` in `DESCRIPTION`.

### Roxygen documentation

- Every exported function should have `@returns` and `@examples`.
- Add `@seealso` only when there is a closely related function worth cross-referencing.
- Markdown formatting is enabled; use it (backticks, bold, etc.) in roxygen prose.

### Commit messages

- Use **freeform imperative mood**: "Add x", "Fix y", "Remove z". No conventional-commit
  prefix required.


===== FILE sugarforever/clawless::CLAUDE.md | stars=1 followers=1051 lang=TypeScript bytes=3580 =====

# Clawless

Tauri v2 desktop app for browsing and resuming OpenClaw sessions across all channels.

## Why

Messaging channels (Telegram, WhatsApp, Slack) don't let you re-enter old OpenClaw sessions. Once a conversation scrolls away, you lose context and can't continue where you left off. Clawless solves this by connecting directly to the OpenClaw gateway, listing all historical sessions from every channel, and letting you open any one to continue chatting.

## Architecture

See @ARCHITECTURE.md for full design. Key points:

- Connects to OpenClaw gateway via WebSocket at `localhost:18789`
- No channel plugin needed; uses the same protocol as the Mac menubar app
- Gateway methods: `sessions.list`, `chat.history`, `chat.send`, `chat.abort`
- Push events: `chat` (streaming deltas/finals), `agent` (tool events), `tick` (heartbeat)

## Tech Stack

- **Tauri v2** (Rust backend, web frontend)
- **SvelteKit** (frontend framework)
- **TypeScript** (strict, no `any`)
- **Tailwind CSS** (styling)

## Project Structure

```
src/
  lib/
    gateway.ts          # WebSocket client, reconnection, auth
    sessions.ts         # Session list, search, sort
    chat.ts             # Send/receive/stream messages
    types.ts            # Protocol types
  routes/
    +layout.svelte      # App shell with sidebar
    sessions/+page.svelte   # Session browser
    chat/[key]/+page.svelte # Chat view
  components/
    SessionList.svelte
    ChatMessage.svelte
    ChatInput.svelte
    StreamingText.svelte
src-tauri/                # Rust/Tauri backend
```

## Build & Dev Commands

- Install deps: `pnpm install`
- Dev: `pnpm tauri dev`
- Build: `pnpm tauri build`
- Type-check: `pnpm check`
- Format: `pnpm format`

## Coding Style

- TypeScript strict mode; avoid `any`
- Svelte 5 runes (`$state`, `$derived`, `$effect`) over legacy stores
- Prefer composition over inheritance
- Keep components under 200 lines; extract helpers when they grow
- Use Tailwind utility classes; avoid custom CSS unless necessary
- Brief comments only for non-obvious logic

## Gateway Protocol Reference

Frame format (JSON over WebSocket):
```
Request:  { type: "req", id: string, method: string, params: object }
Response: { type: "res", id: string, ok: boolean, payload?: object, error?: { code, message, details? } }
Event:    { type: "event", event: string, payload: object, seq: number }
```

Connection flow: connect → send `connect` request (with `minProtocol`, `maxProtocol`, `client` object with `id` from allowed client IDs, `mode` from allowed modes) → receive hello-ok with `protocol`, `server`, `snapshot`, `features`, `policy`.

Chat event states: `delta` (streaming chunk), `final` (complete), `aborted`, `error`.

## OpenClaw Reference Files

When investigating gateway protocol details, read these files in the OpenClaw repo (`../openclaw/`):

- `src/gateway/server-chat.ts` — chat method implementations
- `src/gateway/server-methods/sessions.ts` — session list/resolve/preview
- `src/gateway/protocol/` — protocol frame types
- `apps/macos/Sources/OpenClaw/GatewayConnection.swift` — Mac app WS client (reference impl)
- `src/config/sessions/types.ts` — SessionEntry type definition

## Design Principles

- Session resumption is the core feature; optimize for browsing and re-entering old conversations
- Always generate idempotency keys (UUID) for `chat.send` to prevent duplicates
- Handle WebSocket disconnection gracefully with auto-reconnect
- Show streaming text as it arrives; don't wait for final
- Keep the UI minimal and fast; this is a power-user tool


===== FILE stevekinney/scrumlord::CLAUDE.md | stars=1 followers=3495 lang=TypeScript bytes=8367 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Development

```bash
bun run dev               # Start development with watch mode
bun run build             # Build for production (outputs to dist/)
bun ./dist/bun/index.js   # Run Bun-optimized build
node ./dist/node/index.js # Run Node-compatible build
```

### Testing

```bash
bun test                  # Run all tests
bun test src/utils        # Run tests in specific directory
bun test logger           # Run tests matching pattern
bun test --watch          # Watch mode
bun test --coverage       # Generate coverage report
```

### Code Quality

```bash
bun run lint             # Check linting errors
bun run lint:fix         # Auto-fix linting errors
bun run typecheck        # TypeScript type checking (src + scripts)
bun run typecheck:test   # TypeScript type checking (test files)
bun run format           # Format all files with Prettier
bun run format:check     # Check formatting without changes
bun run check            # Fast local sanity: format:check + lint + typecheck
bun run validate         # Full gate: format:check + lint + typecheck + typecheck:test + test + build + package:check
```

### Utilities

```bash
bun run clean            # Clean build artifacts (dist/, coverage/, caches)
bun run package:check    # Run publint + @arethetypeswrong/cli on packed tarball
```

## Architecture Overview

### Core Design Principles

1. **Environment-First Configuration**: All configuration starts with environment variables validated through Zod schemas in `src/environment.ts`. The `environment` object is the single source of truth.

2. **Lean Surface Area**: This template intentionally avoids framework-specific scaffolding (custom error classes, logger wrappers, etc.). Add only what you need for your project.

3. **Runtime-Neutral Published Code**: `src/` must not use Bun-only runtime APIs (`Bun.file`, `Bun.env`, `Bun.serve`, etc.). Those APIs are fine in `scripts/` and test files, but must not appear in published library output.

### Key Notes

- **ESM + TypeScript**: Source files are TypeScript modules; build output targets both Node and Bun.
- **Import paths**: Use standard TS/ESM imports; no `@/*` path alias (it leaks into `.d.ts` files).
- **Library output**: Dual-emit — `dist/node/` for Node consumers, `dist/bun/` for Bun consumers. The `exports` map routes consumers automatically.

### Library Packaging

The build produces:

- `dist/node/index.js` — ESM bundle, `Bun.build target: 'node'`, all deps external
- `dist/bun/index.js` — ESM bundle, `Bun.build target: 'bun'`, all deps external
- `dist/index.d.ts` — TypeScript declarations (shared)

The `exports` map in `package.json`:

```json
{
  ".": {
    "types": "./dist/index.d.ts",
    "bun": "./dist/bun/index.js",
    "import": "./dist/node/index.js",
    "default": "./dist/node/index.js"
  },
  "./package.json": "./package.json"
}
```

Package validation runs as part of `validate`: `publint` checks the exports map structure and `@arethetypeswrong/cli` checks type resolution across resolution modes.

### Git Hooks Architecture

Hooks are configured in `lefthook.yml` and implemented as Bun TypeScript files under `scripts/hooks/`:

- **pre-commit** (`lefthook.yml` inline, piped/sequential): formats staged files with Prettier, runs oxlint --fix on staged files, checks `bun.lock` is staged when `package.json` changes. Fast by design.
- **pre-push** (`lefthook.yml`): runs full `bun run validate`.
- **post-checkout** (`scripts/hooks/post-checkout.ts`): installs deps when `package.json`+`bun.lock` change; surfaces config changes.
- **post-merge** (`scripts/hooks/post-merge.ts`): installs/cleans when dependencies or config changed; shows merge stats.

They use `chalk` for color, `change-case` for headings, and Bun's `$` and `Bun.write` for shell/IO.

### Types

There is no shared `src/types.ts` in this template. Add shared or domain-specific types near their modules as needed.

## Development Patterns

### Adding New Features

1. **Environment variables**: Add to `.env.example` first, then update the schema in `src/environment.ts`.
2. **Types**: Domain-specific types live near their modules.
3. **Keep the plugin skills in sync**: Whenever you add, rename, remove, or change the behavior of a `tasks` CLI command, flag, or output mode, update the skill source under `src/skills/` in the same change. `src/skills/tasks.md` documents the CLI for the `tasks` skill, and `src/skills/scrumlord-task-manager.md` documents the subagent's setup and decomposition workflow. After editing either file, run `bun run plugin:build` so the regenerated payload under `.claude-plugin/` and `.codex-plugin/` lands in the same commit. The plugin emitters in `src/plugin-emit-claude.ts` and `src/plugin-emit-codex.ts` are driven by `src/plugin-spec.ts` — touch the spec only when you are adding a new skill, agent, hook event, or MCP server, not for prose changes. `bun run plugin:check` (part of `validate`) regenerates the trees and fails if the committed output drifts from the spec, so a stale generated file can never land; when the `claude` CLI is on `PATH` it also runs `claude plugin validate . --strict`.

### Testing Approach

- Tests use Bun's built-in test runner with `describe`, `it`, `expect`.
- Test files are colocated with sources using the `.test.ts` suffix.
- `test/setup.ts` is preloaded by `bunfig.toml` — it resets mocks and system time in `afterEach`. All tests get this automatically.
- Oxlint rules are relaxed for test files. You can use `any`, non-null assertions, and other patterns normally flagged.
- A separate `tsconfig.test.json` provides relaxed TypeScript settings for tests (checked by `bun run typecheck:test`).
- Coverage threshold is 100% for `src/`. Run `bun test --coverage` to see the report.

### Import Organization

Keep imports in this order:

1. Bun built-ins (e.g., `import { file, write } from 'bun'`)
2. Node built-ins (e.g., `import { readFile } from 'node:fs'`)
3. External packages (e.g., `import { z } from 'zod'`)
4. Relative imports (e.g., `./local-module`)

No path alias (`@/*`) — use relative imports everywhere.

## Bun-Specific Considerations

- Always use `bun` commands, not `npm` or `yarn`.
- The lockfile in this repo is `bun.lock`.
- Bun provides native TypeScript execution without precompilation.
- For one-off package execution, use `bun x` for packages already in `devDependencies` rather than `bunx`, which can pull remote versions.

### Prefer Bun Built-ins Over Node

When possible, use Bun's native APIs in `scripts/` and tests. Do not use them in `src/` — published code must be Node-compatible.

| Task          | Use (Bun)                                | Avoid (Node)                     |
| ------------- | ---------------------------------------- | -------------------------------- |
| Read file     | `Bun.file(path).text()`                  | `fs.readFileSync(path, 'utf-8')` |
| Write file    | `Bun.write(path, data)`                  | `fs.writeFileSync(path, data)`   |
| HTTP server   | `Bun.serve()`                            | `http.createServer()` or Express |
| Hashing       | `Bun.hash()` or `new Bun.CryptoHasher()` | `crypto.createHash()`            |
| Spawn process | `Bun.spawn()` or `Bun.$`                 | `child_process.spawn()`          |
| Sleep         | `Bun.sleep(ms)`                          | `setTimeout` with promisify      |
| Environment   | `Bun.env.VAR`                            | `process.env.VAR`                |
| Glob          | `Bun.Glob`                               | `glob` package                   |

When a Bun equivalent doesn't exist or Node's API is more appropriate, use the `node:` prefix for clarity (e.g., `import { join } from 'node:path'`).

### Configuration Notes

- **bunfig.toml**: Configures the `.md` text loader, forces Bun runtime for scripts, and sets up `bun test` with preload, coverage, and 100% thresholds.
- **TypeScript**: Uses Bun types; Node type libs are not included by default.
- **Oxlint**: Rust-based linter with built-in TypeScript, promise, unicorn, and import plugins. Type-aware rules enabled via `--type-aware --tsconfig ./tsconfig.json`. Test files have relaxed rules.
- **Testing**: Run tests in parallel via `bun test --parallel`.


===== FILE tr4m0ryp/clay-enrichment::CLAUDE.md | stars=1 followers=1609 lang=Python bytes=4758 =====

# Clay Enrichment -- Project Instructions

## CRITICAL: Iteration loop hard rules

**Rule 1 -- Never block on long-running commands.**
Pipeline runs, full re-deploys, multi-minute tests must NOT be invoked with a foreground long timeout. That wastes the budget.
- Launch as a background process (`run_in_background: true`, `nohup ... &`, systemd, or equivalent), capture PID and log path.
- Poll periodically (every 30-60s) by tailing the log or checking process status.
- Block briefly on the poll, not on the run.
- While waiting, work in parallel: review prior outputs, code review, fixes.

**Rule 2 -- Never send actual emails without explicit approval.**
Email sending is the ONLY pipeline stage that must NOT be exercised end-to-end during development / iteration loops.
- Stub, mock, or dry-run the send step so messages are generated and logged but not delivered.
- Verify the generation, templating, personalization, and queueing logic; just don't hit the real SMTP send.
- Every other stage (gathering, LinkedIn matching, company enrichment, personal enrichment, context collection, scoring, etc.) should be fully exercised against real systems.
- Hard kill switch: `EMAIL_SEND_DISABLED=true` in the runtime env makes the email_sender worker skip dispatch even if SMTP creds are present.

## CRITICAL: Server-First Workflow

This project runs on the GCP server, NOT locally. Local development should only be used for code changes. After every change:

1. Commit and push to GitHub
2. Deploy to server: `gcloud compute ssh searxng --zone=europe-west1-b --command="/opt/clay-enrichment/deploy.sh"`

Do NOT run the pipeline or Next.js app locally -- it will exhaust the local machine. The server handles all execution.

## GCP Server Access

- **Provider:** Google Cloud Platform
- **Project ID:** marketing-team-not-needed
- **Account:** m.ouallaf007@gmail.com
- **Instance:** searxng
- **Zone:** europe-west1-b
- **Machine type:** e2-micro (1.9GB RAM + 2GB swap)
- **Internal IP:** 10.132.0.2
- **External IP:** ephemeral (check with `gcloud compute instances describe searxng --zone=europe-west1-b --format="get(networkInterfaces[0].accessConfigs[0].natIP)"`)
- **SSH:** `gcloud compute ssh searxng --zone=europe-west1-b`
- **Run remote command:** `gcloud compute ssh searxng --zone=europe-west1-b --command="<cmd>"`
- **PATH requirement:** `export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"` before using gcloud

## Server Stack

- **PostgreSQL 14** -- clay_enrichment database, user: clay
- **Python 3.10** -- pipeline in /opt/clay-enrichment with .venv
- **Node.js 20** -- Next.js frontend in /opt/clay-enrichment/web
- **Nginx** -- reverse proxy on port 80 -> Next.js port 3000
- **Docker** -- SearXNG meta-search on port 8888
- **Web UI:** http://<external-ip>/ (dashboard)
- **SearXNG:** http://<external-ip>:8888 (internal search engine)

## Systemd Services

- `clay-web` -- Next.js frontend (port 3000, proxied by Nginx)
- `clay-pipeline` -- Python enrichment pipeline
- `postgresql` -- Database
- `nginx` -- Reverse proxy

Common commands (run on server):
```
sudo systemctl status clay-web clay-pipeline
sudo systemctl restart clay-web
sudo systemctl restart clay-pipeline
sudo journalctl -u clay-pipeline -f  # tail pipeline logs
sudo journalctl -u clay-web -f       # tail web logs
```

## Deploy Workflow

After pushing code to GitHub:
```
export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"
gcloud compute ssh searxng --zone=europe-west1-b --command="/opt/clay-enrichment/deploy.sh"
```

The deploy script:
1. git pull
2. pip install -r requirements.txt
3. npm install + next build
4. Restart clay-web service

## Database

- **Connection:** postgresql://clay:clay_enrichment_2026@localhost:5432/clay_enrichment
- **Schema:** schema/001_init.sql (5 main tables + 2 join tables)
- **Tables:** campaigns, companies, contacts, emails, contact_campaigns, company_campaigns, contact_campaign_links
- **Access from Python:** asyncpg via src/db/
- **Access from Next.js:** postgres.js via web/src/lib/db.ts

## Project Structure

```
clay-enrichment/
  src/           -- Python pipeline
    db/          -- Postgres data layer (asyncpg)
    layers/      -- Worker modules (discovery, enrichment, research, scoring, email)
    models/      -- Gemini client
    prompts/     -- LLM prompts
    search/      -- SearXNG, Brave, scraper
    discovery/   -- Contact finder, email permutation, SMTP verify
    email/       -- SMTP sender
  web/           -- Next.js frontend (avelero style)
    src/app/     -- Pages (App Router)
    src/components/ -- UI components
    src/lib/     -- DB connection, queries, utils
  schema/        -- SQL migrations
  scripts/       -- Utility scripts
  deploy.sh      -- Server deploy script
```


===== FILE PramodDutta/TheTestingAutomationAcademy::CLAUDE.md | stars=1 followers=1873 lang=TypeScript bytes=2620 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Marketing website for TheTestingAutomationAcademy — a software testing training platform offering LIVE classes in manual testing, API testing, and automation testing. Built as a single-page application with client-side routing.

## Commands

- **Dev server**: `npm run dev` (Vite, default port 5173)
- **Build**: `npm run build` (runs `tsc -b && vite build`, output to `dist/`)
- **Lint**: `npm run lint` (ESLint with TypeScript + React hooks rules)
- **Preview production build**: `npm run preview`

No test runner is configured.

## Architecture

### Tech Stack
- React 19 + TypeScript + Vite 7
- Tailwind CSS 3 with shadcn/ui (New York style, `slate` base color)
- react-router-dom v7 with `HashRouter` (hash-based routing for static hosting)
- All pages are lazy-loaded via `React.lazy()` in `App.tsx`

### Path Alias
`@/` maps to `./src/` — configured in both `tsconfig.json` and `vite.config.ts`.

### Key Directories
- `src/pages/` — Route-level page components (Home, Courses, CourseDetail, Blog, BlogPost, Contact, etc.)
- `src/components/ui/` — shadcn/ui primitives (50+ components, managed via `npx shadcn-ui` per `components.json`)
- `src/components/layout/` — `Navbar.tsx` and `Footer.tsx`, rendered globally in `App.tsx`
- `src/data/courses.ts` — Course catalog with typed `Course` and `Lesson` interfaces; all course data is hardcoded here
- `src/mocks/react-router-dom.tsx` — Custom minimal router mock (not used in production; `main.tsx` uses the real `react-router-dom`)
- `src/lib/utils.ts` — Single `cn()` utility combining `clsx` + `tailwind-merge`
- `src/hooks/use-mobile.ts` — Mobile breakpoint detection hook

### Routing
Routes are defined in `App.tsx`. Notable dynamic routes:
- `/courses/:slug` — `CourseDetail` page, slug matches `Course.slug` from `src/data/courses.ts`
- `/blog/:id` — `BlogPost` page

### Design System
`Design.md` contains the full design specification including brand colors (Gold `#FFD700`, Dark Blue `#001F3F`), typography (Poppins for headings, Open Sans for body), animation choreography per section, and responsive breakpoints. Reference this when making visual changes.

### Styling Conventions
- Tailwind utility classes directly in JSX; use `cn()` from `@/lib/utils` for conditional classes
- CSS variables for theming defined in `src/index.css` (HSL format for shadcn compatibility)
- Brand-specific colors are applied inline (e.g., `bg-[#FFD700]`, `text-[#001F3F]`) rather than via the Tailwind theme


===== FILE hadley/data-editor::CLAUDE.md | stars=1 followers=26707 lang=TypeScript bytes=785 =====

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
specs/001-data-entry-tool/plan.md

Active feature: Herringbone — browser-based, spreadsheet-style editor
for single-table Parquet data driven by a `data-dict.yaml` dictionary.
Shell: Tauri 2 (Rust) desktop app for macOS — reliable in-place save; browser-runnable for dev.
Stack: React + Vite + TypeScript, Glide Data Grid, hyparquet(+writer), js-yaml, Zod.
Core invariant: one parsed `Column[]` feeds three pure functions
(toArrow / toValidators / toColumns) so schema, validation, and UI cannot drift.
See also: specs/001-data-entry-tool/{research.md,data-model.md,contracts/,quickstart.md}
<!-- SPECKIT END -->


===== FILE dwmkerr/signalbox::CLAUDE.md | stars=1 followers=1126 lang=TypeScript bytes=7549 =====

# signalbox

A local-first events board for AI coding agents. One board for every agent,
terminal, and job you run.

## Specs are the source of truth - keep them current

**Whenever you change behaviour, update the spec in the same change.** The specs
in `components/specs/` describe the contract; they must never lag the code.

- `components/specs/cli.md` - every CLI command, flag, and its output. Update it
  when you add/rename/remove a command or flag, or change what a command prints.
- `components/specs/events.md` - the wire schema (event types, fields, reducer
  rules). Update it when the event shape or reducer behaviour changes.
- `components/specs/adapters.md` - how each agent adapter fires events.
- **`components/specs/*.html` are the living spec for the app's UI surfaces** -
  the HTML mock IS the source of truth for that surface, not just an
  illustration:
  - `components/specs/settings.html` - the Settings window (every control, its
    label, caption, and the settings-storage table). Change a setting -> update
    this.
  - `components/specs/hub-jumplist.html` - the jumplist (rows, keys, footer,
    marks).
  - `components/specs/menubar.html` - the menu bar icon + dropdown.
  When you add/change/remove a control or behaviour on one of these surfaces,
  update its HTML mock in the same change.

If a change touches behaviour and you did not touch a spec, that is a bug in the
change. Treat "code and spec disagree" as a failing state.

## Layout

- `components/cli/` - the TypeScript CLI + hub, compiled to a single binary with
  Bun (`bun build --compile`). The hub is `signalbox hub` (same binary).
- `components/app/` - the Swift macOS menu bar app (jumplist, status icon,
  settings). The app OWNS the hub: it spawns `signalbox hub` as a child,
  keeps it alive, and stops it on quit (Hub.swift) - there is no LaunchAgent.
  The bundle embeds the CLI at Contents/Resources/signalbox. Built via
  `components/app/Makefile` (it works around a CommandLineTools SPM manifest
  bug - use `make -C components/app build`, not bare `swift build`).
- `components/cli/adapters/` - per-agent hooks/plugins (claude, opencode, pi) and
  tmux.
- `components/scripts/` - dev helpers (e.g. `demo.sh` seeds a board via `fire`).
- `packaging/` - the Homebrew formula template.
- `docs/`, `components/specs/` - docs site and specs.

## Build & test

```bash
make build                     # compile the CLI to components/cli/bin/signalbox
make -C components/app build   # build the menu bar app
cd components/cli && bun test  # CLI + reducer tests
cd components/cli && bunx tsc --noEmit   # typecheck
```

`~/.local/bin/signalbox` is symlinked to `components/cli/bin/signalbox`, so
`make build` deploys the CLI. The app supervises the hub: `make install` kills
a running hub and the app respawns it with the new build within seconds;
relaunch the app itself to pick up an app rebuild.

### Regenerating the hero gif

`docs/images/hero-anim.gif` (README + `docs/assets/hero-images/hero.html` on
the landing page) is a rendered capture of `hero.html`'s `.split` element, not
hand-edited. The README embeds it with `<img width="900">`, but the gif's own
pixel dimensions must NOT be 900-wide - see the resolution note below. After
changing `hero.html`, regenerate it:

```bash
# serve the file (file:// is blocked by headless browsers)
cd docs/assets/hero-images && python3 -m http.server 8791 &

# one-off Playwright + gifsicle install, in a scratch dir (gitignored)
mkdir -p scratch/hero-gif && cd scratch/hero-gif
npm init -y && npm install playwright && npx playwright install chromium
brew install gifsicle   # if not already on the machine
```

Capture script (`scratch/hero-gif/capture.js`) - steps through the CSS
animation with `Animation.currentTime` rather than waiting in real time, so
every frame is exact regardless of machine speed. `deviceScaleFactor: 2`
renders at 2x pixel density (retina-equivalent):

```js
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const OUT_DIR = path.join(__dirname, 'frames');
const URL = 'http://localhost:8791/hero.html';
const DURATION_MS = 9000; // must match the CSS animation's total loop length
const FPS = 12;
const FRAME_COUNT = DURATION_MS / 1000 * FPS;

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1300, height: 1000 }, deviceScaleFactor: 2 });
  await page.goto(URL);
  await page.waitForTimeout(200);
  await page.evaluate(() => document.getAnimations().forEach(a => a.pause()));
  const split = await page.$('.split');
  for (let i = 0; i < FRAME_COUNT; i++) {
    const t = (i * DURATION_MS) / FRAME_COUNT;
    await page.evaluate((t) => {
      document.getAnimations().forEach(a => { a.currentTime = t; });
    }, t);
    await split.screenshot({ path: path.join(OUT_DIR, `frame-${String(i).padStart(3, '0')}.png`) });
  }
  await browser.close();
})();
```

```bash
node capture.js   # frames land at ~2120x888 (native .split size x2)

# Resolution note: do NOT scale down to the README's display width (900).
# The capture is already 2x-supersampled for antialiasing quality, but if you
# then shrink the output back to 900-wide you throw away exactly the pixels
# that bought you - text goes soft again. Ship at 2x the display width
# (1800x754) instead; the <img width="900"> tag downscales it in-browser,
# same as a retina screenshot.
ffmpeg -y -framerate 12 -i frames/frame-%03d.png \
  -vf "scale=1800:754:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:max_colors=255[p];[b][p]paletteuse=dither=none" \
  -loop 0 hero-anim-full.gif

# dither=none avoids visible bayer/floyd-steinberg speckle noise on the flat
# dark background at 8-bit palette depth. But 2x resolution roughly triples
# raw file size (~14MB) - claw it back with gifsicle's lossy compression,
# which targeted-blurs only where the palette would otherwise dither:
gifsicle -O3 --lossy=120 hero-anim-full.gif -o hero-anim.gif   # ~9-10MB

cp hero-anim.gif ../../docs/images/hero-anim.gif
kill %1   # stop the http.server
```

Sanity-check before committing: extract a frame (`ffmpeg -i hero-anim.gif
-update 1 -vframes 1 frame0.png`) and crop a patch of small text at native
resolution (no resizing the crop) - it should read like a real screenshot,
not a soft downscale, and a patch of flat background should show no dither
speckle.

### Testing coding-agent integrations

Use `shellwright` to test a coding agent end to end: it runs the agent (codex,
claude, ...) as a driven shell session so you can send input, read the streamed
output, and take screenshots along the way. This is the way to verify an adapter
against a real agent (e.g. confirm a Codex turn fires the hooks and the board
updates), rather than only feeding canned hook payloads to `signalbox hook`.

## Conventions

- Push to GitHub at the end of the day only - commit locally as you go, one
  push when the day's work is done.
- Conventional Commits (`feat:`, `fix:`, `docs:`, ...).
- Comments explain *why*, not *what* - no breadcrumb comments.
- Use a regular hyphen (-), never an em-dash, anywhere in code, comments, or docs.
- User config: JSON agent configs (Claude settings.json, Cursor hooks.json)
  are merged only with consent, with a timestamped backup and an atomic
  parse-validated write; removal reverses exactly that edit (literal
  signalbox commands only). Freeform config (tmux.conf) is never edited -
  print the snippet instead.


===== FILE ErikCH/tanstack-start-nextjs-killer-demo::AGENTS.md | stars=0 followers=1605 lang=TypeScript bytes=677 =====

<!-- intent-skills:start -->
## Skill Loading

Before substantial work:
- Skill check: run `npx @tanstack/intent@latest list`, or use skills already listed in context.
- Skill guidance: if one local skill clearly matches the task, run `npx @tanstack/intent@latest load <package>#<skill>` and follow the returned `SKILL.md`.
- Monorepos: when working across packages, run the skill check from the workspace root and prefer the local skill for the package being changed.
- Multiple matches: prefer the most specific local skill for the package or concern you are changing; load additional skills only when the task spans multiple packages or concerns.
<!-- intent-skills:end -->


===== FILE mauricioaniche/keynote-design-2026-at-icse::AGENTS.md | stars=0 followers=1271 lang=JavaScript bytes=5124 =====

# AGENTS.md

## Project Overview

This repository contains a keynote talk deck and its speaker notes.

- Main deck: `index.html`
- Speaker notes: `speaker-notes.md`
- Presentation framework: Reveal.js assets in `reveal/`

The deck is a single-file HTML presentation with inline styles and slide content. There is no separate build step.

## Talk Context

- This is a keynote, not a paper talk.
- The audience is broad ICSE-style software engineering audience, with many researchers in the room and some industry practitioners.
- The talk should be intellectually sharp, but still generous, accessible, and inviting.
- The talk is based on industry lessons from large-scale systems and long-lived software.

## Core Message

The central thesis of the talk is:

- At scale, the hardest problems are often in architecture, infrastructure, data, time, migration, and coordination, not only in local code structure.
- Design decisions age.
- Refactoring and migration are inevitable.
- Good design is less about timeless elegance and more about reversibility, survivability, and safe change.

## Audience / Tone Guidance

When editing the deck or notes, keep these constraints in mind:

- It is a keynote: aim for strong, memorable ideas rather than dense technical detail.
- The audience includes researchers: avoid sounding anti-academia.
- Provocation is fine, but it should feel constructive, not dismissive.
- Prefer nuance over absolutist claims.
- Avoid turning the research close into a niche tooling wishlist; keep it high-level and relevant to many kinds of researchers.
- The talk should feel confident and opinionated, but not combative.

## Content Priorities

The current narrative emphasizes:

- "Scale" is multi-dimensional: traffic, uptime, data, teams, services, coordination, regulation, and time.
- The cost of change is a more important lens than static code beauty.
- Migration paths, rollout strategies, compatibility periods, and organizational boundaries are part of design.
- Code quality still matters, but the talk is not primarily about local code cleanliness.
- Socio-technical concerns matter: ownership, team boundaries, decision-making, and Conway's Law affect changeability.
- The research close should invite broader engagement with real change in real systems.

## Editing Rules

If you change `index.html`, you must also review and update `speaker-notes.md` in the same session.

Required synchronization rules:

- The speaker notes must follow the exact current slide order.
- Slide additions, removals, or moves must be reflected in the notes immediately.
- Slide numbering in `speaker-notes.md` must stay accurate.
- If slide titles or core claims change, update the matching notes so they are not stale.
- Do not leave the deck and notes semantically out of sync.

## Slide Design Guidance

- Keep slides sparse: one strong idea per slide when possible.
- Prefer short headlines and minimal supporting text.
- Avoid repeating the same idea across too many consecutive slides unless the user explicitly wants more emphasis.
- Use bullets only when the audience needs a list to scan.
- Preserve the keynote rhythm: thesis -> concrete story -> lesson -> broader principle.
- When possible, move to stories and examples early rather than over-explaining the thesis abstractly.

## Speaker Notes Guidance

- Notes should help the speaker land the point of the slide, not restate the slide word-for-word.
- Notes can carry nuance that is too long for the slide, but they must still match the slide's current message.
- Notes should explain transitions between sections when the deck makes a conceptual jump.
- If a slide is provocative, the notes should usually contain the softening nuance.

## Current Structural Intent

Future edits should generally preserve these high-level beats unless the user asks for a larger rewrite:

1. Set context and define what "scale" means.
2. State the thesis that large-scale pain often lives beyond code.
3. Move into concrete migration/change stories early.
4. Treat time and socio-technical factors as part of design.
5. Bridge explicitly into the code-design section.
6. Use the code section to discuss changeability, not code aesthetics alone.
7. Close with practical principles and a broad, inclusive research invitation.

## Things To Watch Out For

- Do not accidentally make the talk say "code quality does not matter."
- Do not let the close become hostile toward researchers.
- Do not bloat the deck with too many near-duplicate principle slides.
- Do not make the slide text more absolute than the notes can defend.
- Do not add detailed technical mechanisms unless they clearly support the keynote story.

## Suggested Editing Checklist

Before finishing a session that changes the talk:

1. Check the slide order in `index.html`.
2. Check that `speaker-notes.md` reflects the same order.
3. Verify the note headings and slide numbers are still correct.
4. Confirm the talk still reads like a keynote, not a lecture or paper.
5. Look for repeated ideas that can be compressed.
6. Make sure provocative lines are balanced by nuance in the notes.


===== FILE eviltester/youtube-oauth::agents.md | stars=0 followers=1001 lang=JavaScript bytes=837 =====

A simple app for viewing youtube subscriptions:

- information (subscriptions, videos) is cached in the browser at the moment - this is to prevent the API calls running out of credits


TODO:


- [] allow offline caching e.g. file based, from server - toggle when page is started



DONE:

- [x] create a simple server wrapper for running the single page app and manage Client Key as Environment variable
- [x] split shorts and videos into a different view - done via rss
- [x] Use RSS feed to get back the list of new videos as the main approach, drop down to API if it fails - this would allow the app to function even if the API key is out of date but subscription cache still exists - rss implemented from service
- [x] single page is getting a little large, split the javascript into sensible included .js files from a /js directory

===== FILE kt3k/ecma262::AGENTS.md | stars=0 followers=1019 lang=HTML bytes=481 =====

## Dev lifecycle

- When changes are made, execute linter and formatter and check errors
- Use `deno fmt` as the formatter (config in `deno.json`); run it from the repo
  root so its excludes apply. Do not hand-format around it.

## Git operations

- Commit messages should follow conventional commits
- PR title also follows conventional commmits
- When opened a new PR, open that URL in browser
- When merging PR, use squash and commit and summarize the contents at merge
  time


===== FILE phodal/vibe-hardware-coding::AGENTS.md | stars=0 followers=20782 lang=Python bytes=22566 =====

# Agent Notes

Recoding changes to the AGENTS.md file for better organization and clarity.

## Hardware Verification Practices

- Keep each hardware lane scriptable from `make`; interactive IDE state is not enough evidence.
- Keep `config/feature-matrix.tsv` current when adding or changing a feature lane, and run `make feature-matrix-check` before claiming coverage across tracked directions.
- Use `make hardware-evidence-audit` before claiming completion across lanes; it exposes missing `Verified Locally` sections and missing smoke-suite evidence.
- Use `make visual-evidence-audit` before claiming camera/OCR coverage across lanes. It checks whether each feature doc records real `camera-ocr` artifacts in `## Verified Locally`, rather than only documenting an optional `*_VISUAL_SMOKE` path, and it reports the latest `camera-ready` preflight plus `camera-diagnose` recommendation when visual suite runs are blocked by the host camera.
- Use `make ok-qoder-evidence` when you need an article-ready AI self-verification chain for the default hello sketch. It writes source/build/upload/serial/camera/OCR artifacts under `docs/evidence/ok-qoder-*`; only call the display visually verified when camera OCR passes, and use `ALLOW_PARTIAL=1` only to preserve failed-camera evidence for debugging or writing.
- Use `make goal-completion-audit` before claiming the full objective is done. It is stricter than evidence presence and keeps partial, external, conditional, and quiet-window lanes from being over-reported as complete.
- Use `make evidence-index` or `make evidence-index-doc` when you need a single handoff/article map across strict completion, feature docs, hardware-suite status, camera/OCR status, and remaining-gate status. This is an index, not a substitute for the strict completion gate.
- Use `make remaining-gates-preflight` to refresh the safe side of the remaining incomplete lanes, then `make remaining-gates-doc` to regenerate the summary from the latest preflight JSON. It runs official audio planning, XiaoZhi non-destructive preflight, and audio VAD preflight with `destructive=0 audio=0`, while recording Web AI Button physical tap as `skipped/manual-required` unless `REMAINING_GATES_ARGS=--include-manual` is passed; it must not be treated as a substitute for physical audio evidence, approved XiaoZhi flash/runtime evidence, or supervised tap evidence.
- Use `make remaining-gates-runbook` to regenerate the supervised operator checklist before handing off the four remaining external/manual gates. The runbook must keep the approval boundaries visible: allowed audio window for official/audio-front-end smokes, explicit XiaoZhi flash approval plus fresh backup, and human tap availability for Web AI Button.
- Prefer a narrow compile/upload/smoke loop before adding abstractions. For this board, clean Arduino CLI builds with dedicated `.arduino-build/<name>` paths avoid cache collisions.
- Serialize hardware uploads for the same USB Serial/JTAG port. Parallel `esptool` runs can fail with an exclusive lock on `/dev/cu.usbmodem83101`.
- Use `make hardware-smoke-list` and `make hardware-smoke-suite HARDWARE_SMOKE_ARGS="--target <id>"` for serialized multi-lane evidence. The default suite is non-audio and disables visual OCR unless `--with-visual` is passed. With `--with-visual`, the suite must run `camera-ready` before target uploads and abort if the host camera cannot save a frame.
- Use `make claude-skill-smoke` when validating that a separate Claude Code agent can follow the repo Skill and run the non-audio visual smoke through the Skill helper. Its default mode uploads only the calibration display sketch, captures camera OCR, and writes a command transcript under `.logs/`; use `CLAUDE_SKILL_SMOKE_MODE=audit` when uploads are not desired.
- Official demos are `conditional` in the feature matrix. To collect suite evidence late at night, run only the default display/serial baseline with `make hardware-smoke-suite HARDWARE_SMOKE_ARGS="--target official-demos --allow-conditional"`; do not broaden that into ES7210/ES8311 audio demo checks.
- Use `make official-coverage` before claiming official demo coverage. It is read-only and shows which vendor examples have build artifacts, source presence, quiet audio marker readiness, and existing physical smoke logs.
- Use `make official-audio-physical-plan` to inspect the official ES7210/ES8311 physical-audio plan without uploading or using audio devices. `make official-audio-physical-smoke` must refuse unless `ALLOW_AUDIO=1`; the ES8311 output demo additionally requires supervised `OFFICIAL_AUDIO_OUTPUT_CONFIRM=heard` because serial `[echo] Echo start` alone is not audible-output proof.
- For official demos that print expected serial text only during `setup()`, use the Python stdlib `scripts/serial-capture.py` path so capture opens before RTS reset; do not flush serial input after reset or the first setup line can be lost.
- Official demo smoke can add camera OCR with `OFFICIAL_VISUAL_SMOKE=1`. The vendor `01_HelloWorld` sketch renders small randomized multi-color text, so a saved camera frame with no exact OCR match is partial evidence only; use `OFFICIAL_VISUAL_STABLE_MARKER=1 OFFICIAL_VISUAL_SMOKE=1 make official-smoke DEMO=01-helloworld` for the staged-only large `OK` OCR gate, and keep serial `loop` as the official runtime gate.
- The official `03-power-axp2101` sketch waits indefinitely in Station Wi-Fi connection when its vendor credentials are not valid. The official runner applies a staged-only `OFFICIAL_POWER_WIFI_TIMEOUT_MS` patch for automation so AP, PMU, and LVGL setup can be physically smoked; treat that as PMU/LVGL evidence, not proof of Station Wi-Fi success.
- XiaoZhi is an audio product lane, but `xiaozhi-inspect`, `xiaozhi-preflight`, `xiaozhi-backup`, `xiaozhi-runtime-check`, `xiaozhi-visual-check`, `xiaozhi-runtime-visual-check`, `xiaozhi-idf-env`, and `xiaozhi-idf-build` are no-audio readiness/runtime checks. They can run without `--allow-audio`; reserve `--allow-audio` for physical microphone/speaker smoke targets. Before any `xiaozhi-flash`, capture the `xiaozhi_preflight_summary`, `xiaozhi_backup_summary`, and `xiaozhi_idf_build_summary` lines so the firmware hash, serial port, esptool path, source marker, current-board rollback image, ESP-IDF status, and source-build artifacts are recorded. After an approved XiaoZhi flash, run `make xiaozhi-runtime-visual-check` before any audio interaction; it resets/captures serial logs, looks for XiaoZhi onboarding or activation markers, then validates the AMOLED through camera OCR while reporting `destructive=0 audio=0`.
- Use `make xiaozhi-readiness` as the default no-audio XiaoZhi safe bundle. It runs preflight, source check, ESP-IDF env/build, and verifies the latest rollback image. Set `XIAOZHI_READINESS_BACKUP=1` immediately before an approved flash when the current board flash must be freshly captured.
- `xiaozhi-preflight` may report `release_source=cache` when GitHub release lookup fails but a matching `.vendor/xiaozhi/firmware/*_<board>.zip` already exists. Treat cache fallback as a resilience path for local readiness, not proof that the cached firmware is the latest upstream release; set `XIAOZHI_RELEASE_CACHE_FALLBACK=0` when live metadata is required.
- For full 16MB flash backups over this USB Serial/JTAG path, the esptool stub reader can stop around 1%; use `xiaozhi-backup` defaults (`--no-stub`, `XIAOZHI_BACKUP_BAUD=115200`) and keep the command quiet until the final `xiaozhi_backup_summary`.
- Official audio demos now have a quiet `make official-audio-preflight` gate. It compiles the ES7210/ES8311 vendor demos and checks source/serial markers, but it must not be treated as physical microphone/speaker evidence.
- Use `--skip-build` only when that lane's `.arduino-build/<name>` artifacts already exist; otherwise upload can fail because `*.partitions.bin` or related build outputs are missing.
- Treat serial output and camera OCR as complementary evidence: serial proves firmware control flow, while camera OCR proves the AMOLED actually renders expected text.
- Treat saved camera frames with failed exact OCR as partial visual evidence, not as camera-verified evidence. `visual-evidence-audit` reports these as `camera-captured-ocr-partial` when the feature doc records the artifact and the failed OCR condition.
- Keep destructive actions explicit. Firmware replacement commands should require a visible confirmation variable or `--yes`.
- Stage vendor sketches instead of editing vendor sources when Arduino CLI requires folder and `.ino` names to match.
- Treat audible audio smokes as disruptive physical tests. Do not run speaker or microphone stimulus tests late at night unless the user explicitly asks for them.
- Prefer silent PMU/IMU/display validation when working late; serial metrics plus camera OCR can still produce strong evidence without using audio devices.
- Use `make audio-afe-readiness` or `make audio-vad-preflight` as the no-audio gate before scheduling `audio-vad-smoke`; they rebuild the ES7210 probe and check artifacts/checker wiring plus `config/audio-afe-profile.tsv` without playing stimulus, uploading firmware, or opening host audio devices.
- Treat `config/audio-afe-profile.tsv` as the audio-front-end contract: ES7210 capture and ESP-SR VAD are implemented, while AEC, noise suppression, and real WakeNet audio frames remain planned until source integration and physical audio evidence exist.

## Current Challenges

- The installed ESP32 Arduino core has no dedicated 1.75C FQBN, so the repo pins a generic ESP32-S3 FQBN with explicit flash/PSRAM/USB options.
- `arduino-cli monitor` can open but capture no bytes on the local USB Serial/JTAG port; raw `stty` plus `cat` is the reliable serial path.
- Camera OCR is sensitive to orientation, focus, glare, and pixel font shape. Use `make camera-aligner` and keep validation text large and simple.
- For AMOLED overexposure or color mismatch, first validate with `DISPLAY_BRIGHTNESS=96 OCR_PREPROCESS_MODE=color CAMERA_EXPOSURE_POINT=0.5,0.65 CAMERA_FOCUS_POINT=0.5,0.65 COLOR_SWATCH_CHECK=1 make visual-smoke`; the calibration sketch renders large `OK` text plus red/green/blue/yellow swatches, and the swatch checker reports the largest connected color blocks, average RGB, centroids, and row/order geometry.
- Vision OCR can misread `AI OK` as `HI OK`; use serial to verify the full payload and OCR a stable subset such as `OK`.
- Vision OCR can also misread `Qoder`/`OK` on the Web AI button screen as variants such as `Goder`, `Gader`, or `Bol` when the AMOLED is blurred or overexposed. Keep the raw screenshot as evidence, but do not claim exact visual OCR success unless the expected marker is actually matched.
- On the offline voice-control screen, prefer OCRing the stable `VOICE` marker instead of `OK`; Vision has read `OK` as `OК` with a non-ASCII K on the current camera mount. Use `OCR_ROTATE=180` when the board text is upside down to the camera.
- For TinyML IMU visual checks, prefer OCRing `TINY` with `OCR_PREPROCESS_MODE=color OCR_SCALE_WIDTH=2400`; gray preprocessing can drop the cyan/red AMOLED text even when the raw camera frame is readable.
- For IMU interaction visual checks, OCR the stable `OK` success marker with `DISPLAY_ROTATION=2 OCR_PREPROCESS_MODE=color OCR_SCALE_WIDTH=2400`; use serial to verify the `STEP` event and other IMU details because text like `IMU`, `MOVE`, and `STEP` is readable to a human but unstable under the current camera/OCR path.
- For Web AI button visual verification, render the post-response success page as low-brightness black background with large `Qoder` and `OK` text. This produced a camera OCR pass where the older green-button success text stayed partial.
- The Web AI button can hit ESP32 `HTTPClient` `-11` read failures if it triggers HTTP immediately after Wi-Fi join. `scripts/web-ai-button-check.py` includes a short post-Wi-Fi settle delay; keep that delay or an equivalent readiness check when tightening this lane.
- For LVGL visual-agent camera checks, keep the low-brightness dark UI (`DISPLAY_BRIGHTNESS=96`) and OCR the large top-layer `OK` marker with color preprocessing and centered focus/exposure. Serial output is the authoritative proof for LVGL tabview, touch registration, chat, cards, settings, and agent thoughts; the older `LVGL` marker was human-readable but Vision could misread it as `FFACT` / `ГACГ`.
- Camera capture has a `CAMERA_CAPTURE_TIMEOUT` guard. If ffmpeg times out before saving a frame, treat it as host camera availability/ownership first, not as board display failure.
- Use `make camera-ready` before any expensive visual smoke when camera availability is uncertain. It is a strict, no-audio Swift capture preflight and fails unless a frame is saved. Use `make camera-diagnose` when OCR capture fails. It records system camera inventory, Swift AVFoundation device status, related camera processes, avfoundation device listing, and video-only capture probes without touching audio input. Set `CAMERA_DIAGNOSE_FFMPEG=0` when you want to avoid even ffmpeg device enumeration. If Swift reports `running=true frames=0 drops=0`, the session started but macOS/USB delivered no video buffers; treat that as a host camera pipeline issue before changing firmware or display code. If `capture_recommendation=no_video_frame_captured_close_camera_apps_or_reconnect_usb_camera`, do not keep rerunning board smokes; close camera-capable apps or reconnect the USB camera first. Run `make camera-reset` to restart macOS camera services and rerun the strict preflight; it does not quit chat apps unless `CAMERA_RESET_QUIT_CHAT_APPS=1` is set.
- `pyserial` is not installed in the current Python, so host relay tools should use stdlib `termios` or document their dependency explicitly.
- Python `audioop` is not available in the current Python, so WAV analysis should use explicit PCM byte parsing or a documented dependency.
- XiaoZhi source currently requires ESP-IDF `>=5.5.2`; the local automation defaults to `.vendor/esp-idf-v5.5.4` and `~/.espressif/python_env/idf5.5_py3.14_env`. If a login shell detects macOS Python 3.9 instead, use `make xiaozhi-idf-env` or `scripts/xiaozhi.sh idf-build` so the script exports the matching Python environment explicitly.
- PMU validation should not require a nonzero battery voltage because the battery connector may be unused; gate on system voltage and use battery voltage as supporting evidence.
- Power lifecycle validation should not require a connected battery by default. `power-lifecycle-smoke` uses serial-preserving DIM/STANDBY/ACTIVE states, so it proves firmware power-control behavior without claiming true ESP32 deep sleep or measured current draw. For visual verification, keep `POWER_LIFECYCLE_VISUAL_SMOKE=1 DISPLAY_ROTATION=2` on the color OCR path with centered focus/exposure because the generic gray OCR path can miss the white `OK` marker.
- Wi-Fi validation should be scan-only by default. Do not hard-code or commit SSIDs/passwords; use `WIFI_TEST_SSID` and `WIFI_TEST_PASSWORD` only for supervised local join checks.
- Store supervised Wi-Fi join credentials only in ignored `.env` files. The Wi-Fi checker redacts the host-side `JOIN` command, but serial output remains the authoritative proof for `connected=1` and IP assignment; camera OCR should validate the stable `OK` subset because the pixel font can misread `JOIN`.
- Touch validation has two levels: default `touch-status-smoke` proves the CST9217 controller is online, while `TOUCH_REQUIRE_EVENT=1` requires a supervised human tap.
- Web AI Button validation also has two levels: `make web-ai-button-smoke` proves the serial-triggered Wi-Fi/HTTP/display path, while `make web-ai-button-tap-smoke` requires a supervised physical AMOLED tap and captures `WEB_AI_TOUCH_EVENT` plus `WEB_AI_TRIGGER source=touch` before accepting the AI response.

## Cloud AI Terminal Direction

- The first self-developed terminal slice uses serial relay control before direct audio streaming. This validates display rendering and host/cloud protocol shape without blocking on ASR/TTS integration.
- The Cloud AI terminal now has a non-audio ASR -> LLM -> TTS pipeline gate. Preserve `ASR:`, `LLM:`, `TTS:`, and `PIPELINE_DONE` when adding real ES7210/ES8311 streams so late-night validation can still prove protocol behavior without audio devices.
- The Cloud AI terminal has a verified non-audio control-plane gate. Preserve `SESSION:`, `CLOUD:REQ`, `CLOUD:ERR`, `METRICS?`, `CACHE:*`, and `STATE?` commands when adding network or audio paths so session/cloud/cache/state behavior remains testable without cloud credentials or audio devices.
- Move from mock/HTTP text responses to ES7210 microphone capture in small steps: first validate RMS/peak metrics, then require VAD speech, then stream audio for ASR.
- VAD is stricter than raw microphone capture. Treat RMS/peak threshold increases as the microphone data-flow gate, and use `AUDIO_VAD_REQUIRE_SPEECH=1` only when the host speaker is physically close enough.
- On the current desk setup, macOS `say` produced a clear ES7210 signal delta but did not trigger ESP-SR VAD; this is acceptable for the microphone data-flow gate but not for a wake-word or speech-command gate.
- ES8311 playback now has a board-generated tone probe and a host microphone gate. Treat the current gate as physical output evidence, not as proof of TTS quality or frequency accuracy.
- AXP2101 + QMI8658 now have a silent sensor-status probe. A stationary board should report accelerometer magnitude near 1 g; use the wider default range only as a smoke gate.
- The power lifecycle probe is the preferred P1 battery/low-power control gate. Keep its default path silent and serial-driven; only enable `POWER_REQUIRE_BATTERY=1` when a battery is physically connected.
- CST9217 touch now has a silent controller-online probe. Do not claim end-to-end touch UX without either the official LVGL widgets pass or a `TOUCH_REQUIRE_EVENT=1` manual tap pass.
- The LVGL visual-agent harness is the repo-owned proof for LVGL UI beyond vendor examples. Prefer it when validating chat/card/settings UI behavior; keep the official `05-lvgl-widgets` demo as the vendor baseline.
- The interaction dashboard is the preferred combined non-audio app smoke. It verifies display, touch-controller presence, PMU, and IMU through serial page switching plus optional OCR, without requiring a human tap or using any audio device.
- The interaction dashboard also has first-pass P1 behavior for IMU gestures and power management. Default automation uses serial-simulated gestures and power commands for determinism; real physical shake evidence should be reported separately as `DASH_GESTURE source=imu`.
- The IMU interaction probe is the dedicated P1 gate for wrist wake, shake-to-switch, posture menu, and step counting. Keep deterministic serial `SAMPLE:` vectors as the Skill-facing path; report live physical movement evidence separately when a human can move the board.
- The LVGL visual-agent harness is the preferred P1 touch UI / visual-agent slice. It uses real LVGL widgets and a serial protocol for chat bubbles, cards, settings, and agent thoughts, so UI behavior can be tested without network or audio dependencies.
- The desk widget is the first completed P1 desktop-widget slice. It is intentionally serial-driven before direct Wi-Fi integrations, and has a host relay that maps mock, JSON, or HTTP events into CI/GitHub/calendar/timer/LLM widget commands without credentials or audio devices.
- The IoT control panel is the first P1 Home Assistant/MQTT/HTTP slice. Its host relay maps mock, JSON, or HTTP smart-home events into the panel protocol, and Home Assistant events must use `IOT:HA` so the board emits `IOT_HA` plus a `ha=` state counter. Keep that board-visible event boundary before moving logic fully onto Wi-Fi firmware.
- For IoT panel visual checks, OCR the stable `IOT` marker on the returned home page; use serial output as the authoritative proof for device, Home Assistant, MQTT, HTTP, and scene state.
- The Wi-Fi connectivity probe is the network hardware gate for Cloud AI, desktop widget, and IoT work. Prefer it before debugging HTTP/MQTT application logic, and avoid logging nearby SSID names unless the user explicitly needs that evidence.
- The offline voice-control harness is a P1 non-audio gate for WakeNet/MultiNet behavior. Preserve the serial `WAKE:`, `CMD:`, `ADDCMD:`, `MODCMD:`, and `DELCMD:` simulation path when adding real ESP-SR audio so late-night validation can still prove the command state machine without microphone or speaker use.
- The TinyML IMU classifier now has a checked-in nearest-centroid model in `config/tinyml-imu-model.json`. Run `make tinyml-imu-model-check` before board smoke, and keep deterministic serial `SAMPLE:` vectors as the Skill-facing acceptance path even after replacing the embedded model with ESP-DL or a larger trained model.
- The ESP-Claw/OpenClaw agent harness is a P2 compatibility path, not the official ESP-Claw firmware. Preserve the serial `LUA:LOAD`, `RULE:ADD`, `MCP:REGISTER`, `MCP:CALL`, `MEM:PUT`, `MEM:GET`, and `EVENT` gates so Skill automation can prove sense/reason/decide/act behavior without IM credentials, Wi-Fi, camera, or audio.
- For ESP-Claw/OpenClaw visual checks, OCR the stable `OK` marker with `DISPLAY_BRIGHTNESS=96 OCR_PREPROCESS_MODE=color OCR_SCALE_WIDTH=2400`; use serial output as the authoritative proof for local rules, MCP calls, IM chat, memory, and LLM fallback because `AGENT` can still be misread on the current camera/font path.

## Feature Push README Hook

- This repo uses `.githooks/pre-push`; install it with `make install-hooks` or `git config core.hooksPath .githooks`.
- Run `make hook-smoke` after changing `.githooks/pre-push`, `scripts/update-readme-for-feat-push.sh`, or the generated README marker block. It validates both the no-op and feat-triggered paths in a temporary worktree.
- When an outgoing push ref or commit subject includes `feat`, the hook must update the generated `README.md` section between `<!-- feat-push-readme:start -->` and `<!-- feat-push-readme:end -->`.
- Because a pre-push hook cannot add a newly modified `README.md` to the already prepared push, the hook intentionally stops that push after updating the file. Commit the README change, then push again.
- AI agents changing feature behavior should keep `README.md` current before committing, and should not remove the generated marker block unless they also replace the hook behavior.


===== FILE justjavac/blog::AGENTS.md | stars=0 followers=17212 lang=TypeScript bytes=6498 =====

<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# zeet.me —— 舰伥的个人博客

Next.js 16.3 预览版（App Router + Turbopack）+ Tailwind CSS v4 + shadcn/ui（base-nova 风格，基于 @base-ui/react）。全站静态预渲染，支持 PWA 离线访问。

## 常用命令

- `pnpm dev` / `pnpm build` / `pnpm start`：开发、构建、生产运行
- `pnpm lint`：ESLint（v16 已移除 `next lint`，直接用 eslint）
- `pnpm icons`：重新生成 `public/icons/` 下的 PWA 图标（`scripts/generate-icons.mjs`，零依赖手写 PNG 编码）

## 结构约定

- `content/posts/*.md`：博客文章，frontmatter 含 `title/description/date/tags`（可选 `updated`/`draft`）；新增文章即新增文件，无需改代码
- `content/projects/*.md`：手动维护的项目列表（`name/description/url/language/order`），`lib/projects.ts` 读取，作品页据此渲染（不走 GitHub API）
- `content/about.md`：关于页正文（`title/description` + Markdown body），`app/about/page.tsx` 用 `lib/posts.ts` 的 `renderMarkdown` 渲染
- `lib/posts.ts`：Markdown 管线（remark → rehype，rehype-pretty-code 双主题代码高亮），构建期执行。rehype-autolink-headings 注入标题锚点（悬停显现，样式在 globals.css `.anchor`）；rehype-external-links 让外链新窗口打开。frontmatter 支持 `draft: true`（生产环境隐藏）。`getPrevNext`（上一篇/下一篇）、`getAllTags`（标签页 `/tags/[tag]`，**非 ASCII 标签必须 `decodeURIComponent` 处理 params——该版本 Next 传的是未解码 URL 段**）。文章页代码块复制按钮：`components/code-copy.tsx` 渐进增强注入。正文排版在 globals.css `.article`（18px/1.8 行高）
- `lib/github.ts`：GitHub 资料/仓库数据，`fetch` + `revalidate: 86400`，内置兜底数据保证离线可构建
- `lib/site.ts`：站点元信息唯一来源（名称、域名、社交链接）
- `components/dot-background.tsx`：Cloudflare 风格点阵高亮背景。基层点阵是纯 CSS（`globals.css` 的 `body::before` fixed 伪元素，**不能放 body 背景**：iOS Safari 忽略 `background-attachment: fixed` 会导致两层错位；伪元素 z-index -2，canvas z -1）；Canvas 只画高亮层；点距 `SPACING = 20` 必须与 CSS `background-size: 20px` 保持一致。**按路由分两种模式**（`usePathname`，effect 依赖 `isHome`）：首页全屏高亮（alpha 压到 0.45 保证可读），内容页只在 `<main>` 正文栏之外绘制（运行时测 main 横向范围，alpha 0.6）。`--accent-warm` 是 oklch，必须经探针元素转成 rgb() 再喂给 canvas（部分浏览器 canvas 不认 oklch，会导致高亮层隐形）。**canvas 是可替换元素，`fixed inset-0` 不会拉伸它（宽度回退到位图宽），高分屏下必须显式设 `style.width/height`，否则光斑按 dpr 倍率位移**
- 路由过渡用 React `<ViewTransition>`（`components/directional-transition.tsx` 包每个页面根部，**不要**放 layout）：Link 用 `transitionTypes` 标方向（`nav-forward`/`nav-back`），文章标题是共享元素（`post-title-${slug}`，卡片 ↔ 正文 h1，`text-morph` 配方防文字栅格重影）。共享过渡由 `components/post-title-link.tsx` 按点击时卡片位置**条件触发**：卡片标题低于文章 h1 落点（H1_TOP=156px）才加 `to-post` 类型（向上飞入，符合深入方向感）；卡片贴在视口上方时不加，退化为普通滑动（避免标题「从顶部往下掉」）。需 `experimental.viewTransition: true`（`next.config.ts`）；类型增强在 `types/react-view-transition.d.ts`（@types/react 稳定版未收录 `ViewTransition`/`addTransitionType`）。导航栏用原始 `viewTransitionName: persistent-nav` 隔离出快照。**禁全局 `scroll-behavior: smooth`**：它会把 Next 路由切换的滚动复位变成动画，被 VT 打断后新页面停在随机滚动位置；要平滑滚动用 `window.scrollTo({behavior:"smooth"})`
- `components/site-header.tsx`：客户端组件，`usePathname` 在首页（`/`）返回 null —— 首页是纯个人介绍单屏（大头像脉冲环 `.avatar-pulse`、名字流光 `.text-shimmer`、`typewriter.tsx` 打字机签名、链接芯片、右上角浮动主题开关），无顶部导航。导航项：博客/作品（`/projects`，GitHub 仓库卡）。`site-footer.tsx` 全站页脚：左侧品牌块（头像+名字+标语），右侧导航（博客/作品/GitHub/RSS）
- 品牌触点：导航栏 logo（非首页）、首页单屏、文章头部署名（头像+昵称）、文末 `author-card.tsx` 作者卡、OG 图头像（`opengraph-image.tsx` 构建期拉取转 data URI，失败降级无头像）
- 滚动驱动的浮层（`post-overlay.tsx`/`back-to-top.tsx`）一律用 ref + 内联 style，不用 Tailwind 的 `scale-x-*`/`translate-*` 类：Tailwind v4 的 scale/translate 走原生 `scale`/`translate` 属性，会与内联 `transform` 叠乘。`post-overlay.tsx` 通过 portal 把文章标题注入站点导航栏的 `#post-title-slot` 插槽（`site-header.tsx`，窄屏隐藏），进度线 `fixed top-[54px]` 贴导航栏底边
- `public/sw.js`：手写 Service Worker（核心页预缓存 + 导航 network-first + 静态资源 SWR），仅生产环境注册（`components/register-sw.tsx`）

## 样式约定

- 不引入第三方字体，使用系统字体栈（`globals.css` 中 `--font-sans` / `--font-mono`）
- 主题切换用 next-themes（class 策略），暗色变量在 `.dark` 下；点阵高亮主题色为 `--accent-warm`
- 文章正文排版用手写的 `.article` 样式（未使用 typography 插件）；Shiki 双主题依赖 `.dark` 类选择器

## 注意

- 头像用原生 `<img>` + GitHub CDN 的 `s=` 尺寸参数（`site-header.tsx`、`app/page.tsx`），不走 `/_next/image` 优化器：v16 默认阻止解析到私网 IP 的上游（本机代理 fake-ip 会触发 400），且直连 CDN 更快。若日后改用 next/image，注意 v16 用 `preload` 代替已废弃的 `priority`
- lucide-react 已移除品牌图标，GitHub 图标用 `components/github-icon.tsx`
- OG 图（`app/opengraph-image.tsx`）只渲染英文文本（内置 Geist 字体不含 CJK）


===== FILE AgriciDaniel/reinforcement-learning-second-brain::AGENTS.md | stars=0 followers=2164 lang=Python bytes=1649 =====

# Reinforcement Learning Brain Agent Instructions

The canonical agent entrypoint is `SKILL.md`; this file exists for agent
runtimes that load project-level `AGENTS.md` instructions.

## Read Order

1. `SKILL.md`
2. `README.md`
3. `docs/OPERATOR_KIT.md`
4. `docs/PRODUCT_BOUNDARIES.md`
5. `references/product-spec.md`
6. `references/source-ledger.json`
7. `references/adapter-manifest.json`
8. `agents/reinforcement-learning-secretary.md`

## Operating Rules

- Do not call this brain market-ready unless `scripts/audit_brain.py --require
  market-ready` passes.
- A scaffold is not a finished brain.
- Domain-specific claims require dated trustworthy sources.
- Research evidence must be recorded in `references/source-ledger.json`.
- Adapter completion must be recorded in `references/adapter-manifest.json`.
- Preserve `.raw/` as immutable source material.
- Keep Obsidian `wiki/`, `CODEX.md`, dashboards, canvases, frontmatter,
  wikilinks, graph hygiene, and source citations healthy.
- V1 is advisory and read-only unless a future release defines approval and
  rollback for mutations.
- For grounded answers or vault maintenance, use `agents/reinforcement-learning-secretary.md`.
  It must cite a vault note and an official URL for any domain claim.

## Verification

```bash
python -m compileall scripts reinforcement_learning_brain tests
python tests/test_pipeline.py
python tests/test_adapters.py
python scripts/lint_vault.py --vault assets/template-brain --template
python scripts/build_demo_vault.py
git diff --exit-code -- examples/sample-vault
python scripts/audit_brain.py --json
python scripts/package_release.py --version 1.1.0
```


===== FILE austintgriffith/greeting-demo::AGENTS.md | stars=0 followers=2679 lang=Solidity bytes=7534 =====

# AGENTS.md

This file provides guidance to coding agents working in this repository.

## Project Overview

Scaffold-ETH 2 (SE-2) is a starter kit for building dApps on Ethereum. It comes in **two flavors** based on the Solidity framework:

- **Hardhat flavor**: Uses `packages/hardhat` with hardhat-deploy plugin
- **Foundry flavor**: Uses `packages/foundry` with Forge scripts

Both flavors share the same frontend package:

- **packages/nextjs**: React frontend (Next.js App Router, not Pages Router, RainbowKit, Wagmi, Viem, TypeScript, Tailwind CSS with DaisyUI)

### Detecting Which Flavor You're Using

Check which package exists in the repository:

- If `packages/hardhat` exists → **Hardhat flavor** (follow Hardhat instructions)
- If `packages/foundry` exists → **Foundry flavor** (follow Foundry instructions)

## Common Commands

Commands work the same for both flavors unless noted otherwise:

```bash
# Development workflow (run each in separate terminal)
yarn chain          # Start local blockchain (Hardhat or Anvil)
yarn deploy         # Deploy contracts to local network
yarn start          # Start Next.js frontend at http://localhost:3000

# Code quality
yarn lint           # Lint both packages
yarn format         # Format both packages

# Building
yarn next:build     # Build frontend
yarn compile        # Compile Solidity contracts

# Contract verification (works for both)
yarn verify --network <network>

# Account management (works for both)
yarn generate            # Generate new deployer account
yarn account:import      # Import existing private key
yarn account             # View current account info

# Deploy to live network
yarn deploy --network <network>   # e.g., sepolia, mainnet, base

yarn vercel:yolo --prod # for deployment of frontend
```

## Architecture

### Smart Contract Development

#### Hardhat Flavor

- Contracts: `packages/hardhat/contracts/`
- Deployment scripts: `packages/hardhat/deploy/` (uses hardhat-deploy plugin)
- Tests: `packages/hardhat/test/`
- Config: `packages/hardhat/hardhat.config.ts`
- Deploying specific contract:
  - If the deploy script has:
    ```typescript
    // In packages/hardhat/deploy/01_deploy_my_contract.ts
    deployMyContract.tags = ["MyContract"];
    ```
  - `yarn deploy --tags MyContract`

#### Foundry Flavor

- Contracts: `packages/foundry/contracts/`
- Deployment scripts: `packages/foundry/script/` (uses custom deployment strategy)
  - Example: `packages/foundry/script/Deploy.s.sol` and `packages/foundry/script/DeployYourContract.s.sol`
- Tests: `packages/foundry/test/`
- Config: `packages/foundry/foundry.toml`
- Deploying a specific contract:
  - Create a separate deployment script and run `yarn deploy --file DeployYourContract.s.sol`

#### Both Flavors

- After `yarn deploy`, ABIs are auto-generated to `packages/nextjs/contracts/deployedContracts.ts`

### Frontend Contract Interaction

**Correct interact hook names (use these):**

- `useScaffoldReadContract` - NOT ~~useScaffoldContractRead~~
- `useScaffoldWriteContract` - NOT ~~useScaffoldContractWrite~~

Contract data is read from two files in `packages/nextjs/contracts/`:

- `deployedContracts.ts`: Auto-generated from deployments
- `externalContracts.ts`: Manually added external contracts

#### Reading Contract Data

```typescript
const { data: totalCounter } = useScaffoldReadContract({
  contractName: "YourContract",
  functionName: "userGreetingCounter",
  args: ["0xd8da6bf26964af9d7eed9e03e53415d37aa96045"],
});
```

#### Writing to Contracts

```typescript
const { writeContractAsync, isPending } = useScaffoldWriteContract({
  contractName: "YourContract",
});

await writeContractAsync({
  functionName: "setGreeting",
  args: [newGreeting],
  value: parseEther("0.01"), // for payable functions
});
```

#### Reading Events

```typescript
const { data: events, isLoading } = useScaffoldEventHistory({
  contractName: "YourContract",
  eventName: "GreetingChange",
  watch: true,
  fromBlock: 31231n,
  blockData: true,
});
```

SE-2 also provides other hooks to interact with blockchain data: `useScaffoldWatchContractEvent`, `useScaffoldEventHistory`, `useDeployedContractInfo`, `useScaffoldContract`, `useTransactor`.

**IMPORTANT: Always use hooks from `packages/nextjs/hooks/scaffold-eth` for contract interactions. Always refer to the hook names as they exist in the codebase.**

### UI Components

**Always use `@scaffold-ui/components` library for web3 UI components:**

- `Address`: Display ETH addresses with ENS resolution, blockie avatars, and explorer links
- `AddressInput`: Input field with address validation and ENS resolution
- `Balance`: Show ETH balance in ether and USD
- `EtherInput`: Number input with ETH/USD conversion toggle
- `IntegerInput`: Integer-only input with wei conversion

### Styling

**Use DaisyUI classes** for building frontend components.

```tsx
// ✅ Good - using DaisyUI classes
<button className="btn btn-primary">Connect</button>
<div className="card bg-base-100 shadow-xl">...</div>

// ❌ Avoid - raw Tailwind when DaisyUI has a component
<button className="px-4 py-2 bg-blue-500 text-white rounded">Connect</button>
```

### Configure Target Network before deploying to testnet / mainnet.

#### Hardhat

Add networks in `packages/hardhat/hardhat.config.ts` if not present.

#### Foundry

Add RPC endpoints in `packages/foundry/foundry.toml` if not present.

#### NextJs

Add networks in `packages/nextjs/scaffold.config.ts` if not present. This file also contains configuration for polling interval, API keys. Remember to decrease the polling interval for L2 chains.

## Code Style Guide

### Identifiers

| Style            | Category                                                                                                               |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `UpperCamelCase` | class / interface / type / enum / decorator / type parameters / component functions in TSX / JSXElement type parameter |
| `lowerCamelCase` | variable / parameter / function / property / module alias                                                              |
| `CONSTANT_CASE`  | constant / enum / global variables                                                                                     |
| `snake_case`     | for hardhat deploy files and foundry script files                                                                      |

### Import Paths

Use the `~~` path alias for imports in the nextjs package:

```tsx
import { useTargetNetwork } from "~~/hooks/scaffold-eth";
```

### Creating Pages

```tsx
import type { NextPage } from "next";

const Home: NextPage = () => {
  return <div>Home</div>;
};

export default Home;
```

### TypeScript Conventions

- Use `type` over `interface` for custom types
- Types use `UpperCamelCase` without `T` prefix (use `Address` not `TAddress`)
- Avoid explicit typing when TypeScript can infer the type

### Comments

Make comments that add information. Avoid redundant JSDoc for simple functions.

## Documentation

Use **Context7 MCP** tools to fetch up-to-date documentation for any library (Wagmi, Viem, RainbowKit, DaisyUI, Hardhat, Next.js, etc.). Context7 is configured as an MCP server and provides access to indexed documentation with code examples.

## Specialized Agents

Use these specialized agents for specific tasks:

- **`grumpy-carlos-code-reviewer`**: Use this agent for code reviews before finalizing changes


===== FILE GcsSloop/growth-record::AGENTS.md | stars=0 followers=3280 lang=HTML bytes=4355 =====

# AGENTS.md

This document defines the working rules for AI and human contributors in this repository.

## Mission

Migrate the original single-file personal growth dashboard into a maintainable Cloudflare-native product while preserving the current visual direction and user experience.

## Non-Negotiable Quality Gate

Before every commit, run:

```bash
npm run quality
```

Coverage must stay at or above 85% for lines, statements, branches, and functions. Do not lower thresholds without explicit project-owner approval.

## PDCA Workflow

Every implementation cycle must be small and committed separately:

1. **Plan:** State the cycle objective and files involved.
2. **Do:** Implement only that cycle.
3. **Check:** Run the quality gate and any focused smoke checks.
4. **Act:** Commit with a clear message.

## Architecture Rules

- Worker name is `growth-record`.
- D1 is the source of truth for durable app data.
- User data must always be scoped by `user_id`.
- Admin routes must require an admin role.
- Static web assets live in `public/`.
- Worker API code lives in `src/worker/`.
- Tauri desktop client code lives in `apps/desktop/`.
- Flutter mobile client code lives in `apps/mobile/`.
- Shared type-safe helpers should be small and tested.

## Security Rules

- Never store plaintext passwords.
- Prefer HttpOnly cookies for sessions.
- Treat email addresses and optional phone numbers as user data.
- Usernames are required for admin-created users and must stay globally unique.
- Email registration may omit username; the backend derives the default username from the email prefix.
- Password login must support both email + password and username + password.
- Do not log passwords, session tokens, or API keys.
- Keep `.dev.vars` and `.env*` files out of Git.
- The default admin username is `admin`; the password is configured on first `/admin` visit.
- Admin password recovery must require backend configuration access through `ADMIN_RESET_KEY`.
- Never expose `ADMIN_RESET_KEY` to browser code or public documentation examples with a real value.

## Frontend Rules

- Preserve the dark/gold visual style from `Personal Growth Record-V1.html`.
- Web pages must adapt to mobile, tablet, and desktop.
- `/admin` must match the product style but remain utilitarian and data-dense.
- Avoid large UI rewrites unless the current PDCA cycle explicitly calls for it.

## Mobile Rules

- Flutter apps use native authentication first, then open the authenticated web experience in a WebView.
- The web URL must be configurable for local, staging, and production builds.
- Do not add store publishing metadata until requested.

## Desktop Rules

- Tauri must stay on the 2.x line unless the project owner approves an upgrade.
- macOS and Windows client builds should wrap the same authenticated web app experience.
- Keep Tauri permissions minimal and document any new capability.
- Build platform-specific installers on their target operating systems unless CI cross-compilation is explicitly configured.

## Git Rules

- Keep commits focused to one PDCA cycle.
- Do not rewrite unrelated files.
- Do not remove the original static HTML reference until the migration is complete and approved.
- `master` is protected. Do not push feature work directly after branch protection is enabled.
- Merge pull requests with linear history only. Do not use merge commits.
- The required GitHub status check before merge is `Quality Gate`.

## Automation Rules

- `.github/workflows/ci.yml` runs `npm run quality` on pushes to `master` and pull requests targeting `master`.
- `.github/workflows/deploy-worker.yml` deploys Cloudflare Workers only from tags matching `dpw-v*.*.*`.
- `.github/workflows/release-clients.yml` packages clients only from tags matching `v*.*.*`.
- Release and deploy tags must point to commits contained in `master`.
- Required GitHub secrets for Worker deploy are `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
- Optional GitHub variable for client builds is `GROWTH_RECORD_WEB_URL`.
- Never place real CI secrets, Cloudflare tokens, signing keys, or provisioning profiles in repository files.

## Repository Skills

- Use `skills/deploy-worker/SKILL.md` before deploying the Cloudflare Worker or explaining Worker deployment.
- Use `skills/package-clients/SKILL.md` before building or explaining native client packages.


===== FILE dhellmann/gmail-inbox-summary::CLAUDE.md | stars=0 followers=1148 lang=Python bytes=7186 =====

# Claude Code Instructions

This document contains instructions for working with the Gmail Inbox Summary project using Claude Code CLI.

## Project Overview

Gmail Inbox Summary is a Python application that generates AI-powered summaries of Gmail inbox threads using configurable categorization and Claude Code CLI integration. The project uses Hatch as its build tool and package manager.

## Development Environment Setup

This project uses Hatch for dependency management and task execution. Always use Hatch commands when working with this project:

```bash
# Install dependencies and create environment
hatch env create

# Enter the development shell
hatch shell
```

## Essential Commands

### Running the Application

Always use `hatch run` to execute the application:

```bash
# Generate email summary
hatch run gmail-summary run

# Run with specific configuration
hatch run gmail-summary run --config settings.yml

# Test Claude CLI connection
hatch run gmail-summary test-claude

# Clear cache (useful when data structures change)
hatch run gmail-summary cache clear
```

### Testing and Quality Assurance

Before making commits, always run linting and tests:

```bash
# Run all linting checks
hatch run lint:all

# Run just the linting (faster)
hatch run lint:check

# Fix linting issues automatically  
hatch run lint:fix

# Format code with Ruff
hatch run ruff format

# Run all tests
hatch run test

# Run tests with coverage
hatch run test-cov
```

### Git Workflow

**ALWAYS run tests and linters before committing**. This project uses pre-commit hooks that will enforce these checks, but run them manually first to catch issues early.

Required steps before committing changes:

1. **Run all linters and tests**:

   ```bash
   # Run all linting checks and tests (required before committing)
   hatch run lint:all
   hatch run test
   ```

2. **Fix any linting issues**:

   ```bash
   # Fix automatic formatting issues
   hatch run lint:fix

   # Manually fix any remaining issues reported by lint:all
   ```

3. **Only add the files you actually modified**:

   ```bash
   git add src/gmail_summarizer/file1.py src/gmail_summarizer/file2.py
   ```

4. **Commit with descriptive messages** following the established pattern.

## Project Structure

```text
gmail-inbox-summary/
├── src/gmail_summarizer/
│   ├── config.py              # Configuration management
│   ├── imap_gmail_client.py   # Gmail IMAP integration
│   ├── credential_manager.py  # Secure keychain credential storage
│   ├── thread_processor.py    # Thread categorization and date extraction
│   ├── llm_summarizer.py      # Claude CLI integration
│   ├── html_generator.py      # HTML report generation and template rendering
│   └── main.py               # CLI interface
├── templates/
│   └── summary.html          # Jinja2 HTML template
├── tests/                    # Comprehensive test suite
├── config/                   # Example configurations
└── pyproject.toml           # Project configuration
```

## Key Implementation Notes

### Thread Processing (`thread_processor.py`)

- **Date Extraction**: The `_extract_most_recent_date()` method extracts timestamps from Gmail message data
- **Data Sources**: Uses Gmail API `internal_date` field first, then falls back to parsing `Date` headers
- **Timestamp Format**: Returns millisecond timestamps as integers for consistent sorting

### HTML Generation (`html_generator.py`)

- **Thread Sorting**: Threads are sorted by importance first, then by most recent date (newest first)
- **Template Context**: The `_prepare_template_context()` method handles data preparation for Jinja2
- **Date Formatting**: Custom `format_date` filter provides smart date formatting (time for today, month/day for this year, full date for older messages)

### Template Rendering (`templates/summary.html`)

- **Responsive Design**: Mobile-friendly layout with collapsible categories
- **Date Display**: Shows formatted dates next to thread titles in the metadata section
- **Interactive Features**: JavaScript for category expansion/collapse and keyboard navigation

## Common Development Tasks

### Adding New Features

1. Identify the appropriate module based on functionality
2. Add tests for new functionality first (TDD approach)
3. Implement the feature
4. Update templates if UI changes are needed
5. Run linting and tests before committing

### Debugging Email Processing Issues

1. Use the `--verbose` flag for detailed logging
2. Use `--dry-run` to test categorization without generating summaries
3. Clear cache if data structures have changed: `hatch run gmail-summary cache clear`
4. Check Gmail API data format in debug logs

### Working with Templates

- Templates use Jinja2 with custom filters defined in `html_generator.py`
- CSS is embedded in the template for self-contained output
- Test template changes by regenerating reports with sample data

## Cache Management

The application uses intelligent caching for performance. When modifying data extraction or processing logic:

```bash
# Clear cache to ensure fresh data extraction
hatch run gmail-summary cache clear
```

This is especially important when:
- Adding new fields to thread or message data
- Changing date extraction logic
- Modifying categorization criteria

## Environment and Dependencies

- **Python Version**: 3.12+ required
- **Package Manager**: Hatch (do not use pip directly)
- **Main Dependencies**: Jinja2, PyYAML, BeautifulSoup4, python-dateutil, Click, Rich, Keyring, Pydantic
- **Development Dependencies**: pytest, pytest-cov, ruff, black, mypy, pre-commit

## Best Practices

1. **Always use Hatch**: Run `hatch run` for all Python commands
2. **Test before commit**: Run `hatch run lint:all` AND `hatch run test` before every commit
3. **Fix all issues**: Address all linting and test failures before committing
4. **Clear cache when needed**: Use `hatch run gmail-summary cache clear` after data structure changes
5. **Follow existing patterns**: Study existing code structure before adding features
6. **Use descriptive commit messages**: Follow the established format with clear descriptions
7. **Only commit modified files**: Use `git add` with specific file paths

## Integration with Claude Code CLI

This project is designed to work seamlessly with Claude Code CLI:

- The application uses Claude Code CLI for generating email summaries
- Configuration includes Claude CLI path and timeout settings
- Test Claude connection with: `hatch run gmail-summary test-claude`

## Recent Changes

### Chronological Sorting and Date Display (Latest)

Recent improvements include:

- **Thread Sorting**: Implemented reverse chronological order (newest first) within categories
- **Date Extraction**: Added robust date parsing from Gmail API data with fallback mechanisms
- **Date Display**: Added formatted date display next to thread titles in HTML output
- **Smart Formatting**: Dates show as time (if today), month/day (if this year), or full date (if older)

This enhancement improves user experience by making it easy to identify recent email activity at a glance.


===== FILE m1guelpf/PokeDex::CLAUDE.md | stars=0 followers=3484 lang=Swift bytes=12755 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PokeDex is an iOS app (iOS 26.0+) built with SwiftUI for tracking Pokémon catches across multiple games. It uses SQLite for local storage with a migration system, lazy sprite loading, and supports first-launch onboarding with starter-dependent Pokemon filtering.

## Build & Development Commands

### Building and Running

**IMPORTANT**: Always use MCP tools for building, never use xcodebuild directly.

```bash
# Build and run on a simulator (preferred method)
mcp__xcodebuildmcp__build_run_sim

# Build for device
mcp__xcodebuildmcp__build_device

# Clean build
mcp__xcodebuildmcp__clean
```

### Testing
The project does not currently have a test suite.

### Deployment

**CRITICAL**: Deployment is automated via git push. NEVER push to git to trigger deployment without explicit user authorization. The CI/CD pipeline (Fastlane) handles TestFlight uploads automatically when code is pushed.

## Architecture

### Database Layer (SQLiteData + GRDB)

The app uses a custom migration and seeding system built on top of SQLiteData (Point-Free) and GRDB:

- **Database initialization**: `src/Database/Database.swift:appDatabase()` - Creates the database, registers migrations, and seeds data in preview contexts
- **Migration protocol**: `src/Database/Migration.swift` - Defines `Migration` protocol for schema changes and `Seeder` protocol for data seeding
- **Migrations directory**: `src/Database/Migrations/` - Numbered migration files (e.g., `1_CreatePokemonTable.swift`, `99_Seeder.swift`)
- **Debug behavior**: `eraseDatabaseOnSchemaChange = true` in DEBUG builds automatically resets the database when schema changes

To add a new migration:
1. Create a new file in `src/Database/Migrations/` with naming pattern `{number}_{Description}.swift`
2. Implement the `Migration` protocol with a `static func run(_ db: Database) throws` method
3. Register it in `appDatabase()` by adding it to `migrator.registerMigrations([...])`

### Dependency Injection

Uses Point-Free's swift-dependencies for dependency injection:

- Database and sync engine bootstrapped via `prepareDependencies { try $0.bootstrapDatabase() }` in `App.swift:8-14` and `ContentView.swift:88-91`
- Access database with `@Dependency(\.defaultDatabase) var database`
- Extension in `DependencyValues+database.swift` provides `bootstrapDatabase()` helper

### Data Models

**Database Models** (`src/Models/Database/`):
- **Game**: Multi-game support with `@Table` macro
  - Key fields: `id`, `slug`, `name`, `generation`, `totalPokemon`, `selectedStarter`, `spriteURLTemplate`, `createdAt`
  - `sprite(for: Pokemon) -> URL?`: Generates sprite URL by replacing `{sprite}` placeholder in template
  - `delete(_:)`: Deletes game with cascade to Pokemon and sprite cleanup
  - `static var currentGame`: Query helper for active game from TinyStorage

- **Pokemon**: Pokemon data with `@Table("pokemon")` macro
  - Key fields: `id`, `gameId`, `name`, `dexNumber`, `notes`, `isRegistered`
  - `imageName`: Computed property for sprite filename (e.g., "Mr. Mime" → "mr-mime")
  - `spriteFilePath(for: Game)`: Path to locally cached sprite
  - Uses generic `update(set:)` from `Table+update` extension

**Data Models** (`src/Models/Data/`):
- **GameManifest**: JSON structure for bundled game data
  - Nested: `GameManifest.Game`, `GameManifest.Game.Pokemon`
  - `static func load() throws`: Loads from bundled `games.json`
  - Pokemon filtering: `excludedForStarters` array determines availability based on starter choice

### Views Architecture

**Entry Point**:
- **RootContainer**: Conditional rendering based on game existence
  - `@FetchAll(Game.all)` to check if games exist
  - Shows `SplashScreen` if empty, otherwise `GameScreen`
  - Auto-repairs `activeGameId` in TinyStorage if needed

**Onboarding Flow** (`src/Views/Onboarding/`, `src/Views/Screens/SplashScreen.swift`):
- **SplashScreen**: Welcome screen with sheet presentation
- **GameCreationSheet**: Stage-based onboarding using enum
  - Stages: `.selectingGame`, `.selectingStarter(game)`, `.downloading(progress)`, `.completed`
  - Inline async setup logic (no separate ViewModel or Service)
  - Progress reporting via `AsyncStream` from SpriteManager

**Main Views**:
- **GameScreen**: Main Pokemon list with multi-game support
  - `@FetchAll` with dynamic query based on `currentGameID` binding
  - Toolbar title menu for game switching (tap title → picker + "Add Game")
  - Search, filtering, swipe actions, shake gesture for settings

**Settings** (`src/Views/Sheets/SettingsPage.swift`):
- Clear database functionality
- Displays current game name

**View Extensions**:
- `View+onShake.swift`: Shake gesture support
- `View+if.swift`: Conditional view modifiers

### Sprite Management

**SpriteManager** (`src/Support/SpriteManager.swift`):
- `@MainActor` singleton for thread-safe image caching
- **Lazy loading pattern**: Returns placeholder immediately, downloads in background if missing
- `get(for: Pokemon, in: Game)`: Gets sprite with fallback to placeholder
- `download(for: [Pokemon], in: Game)`: Batch download with progress reporting
  - 50 concurrent downloads (TaskGroup with semaphore pattern)
  - Returns `AsyncStream<Progress>` for UI updates
- `cleanup()`: Removes orphaned sprite directories
- `deleteAll(forGame:)`: Cleans up when game is deleted
- Sprites stored in `Documents/sprites/{gameSlug}/{pokemonName}.png`

### Storage

Uses TinyStorage for lightweight preference storage:
- `@TinyStorageItem(.activeGameId)` - Currently selected game (UUID)
- `@TinyStorageItem(.showingPercentage)` - Toggle percentage vs count display
- `@TinyStorageItem(.showingOnlyMissing)` - Filter to show only uncaught Pokémon
- Extension in `TinyStorage+shared.swift` provides shared storage keys

### Error Handling

Uses Point-Free's IssueReporting:
- Configured with `OSLogIssueReporter()` in `App.swift:8`
- Wrap risky operations with `withErrorReporting { try ... }`
- Logger defined in `src/Support/Logging.swift`

## Key Dependencies (Package.swift)

- **SQLiteData** (Point-Free): Type-safe SQLite wrapper with structured queries
- **GRDB**: Underlying SQLite database engine
- **swift-dependencies**: Dependency injection
- **TinyStorage**: Lightweight UserDefaults wrapper
- **SwiftCSV**: CSV parsing for data import
- **IssueReporting**: Error reporting and logging

## Asset Management

**Static Assets**: `src/Assets.xcassets/`
- Pokeball icon and other UI assets

**Pokemon Sprites**: Downloaded at runtime and cached locally
- Source: `pokemondb.net` (URL template stored in Game model)
- Cache location: `Documents/sprites/{gameSlug}/{pokemonName}.png`
- Lazy loading: SpriteManager returns placeholder immediately, downloads in background
- Sprite filename normalization: Apostrophes removed, spaces/dots → hyphens, ♂ → "-m", ♀ → "-f"

## Code Style & Patterns

### Architectural Preferences

**Prefer inline logic over separate service classes**:
- ✅ Logic in views (e.g., `GameCreationSheet.setup()`) when it's view-specific
- ✅ Static methods on models (e.g., `GameManifest.load()`)
- ✅ Computed properties for derived data (e.g., `Game.sprite(for:)`)
- ❌ Avoid creating dedicated "Manager" or "Service" classes unless shared across many views
- Exception: SpriteManager is justified as a singleton for caching and concurrency control

**Prefer generic extensions over copy-paste**:
- ✅ `Table+update` extension for all PrimaryKeyedTable types
- ✅ Generic helpers in `Extensions/` instead of per-model methods

**Stage-based state machines in views**:
- ✅ Use enums with associated values for multi-stage flows (e.g., `GameCreationSheet.Stage`)
- ✅ Inline state management instead of separate `@Observable` classes when scoped to one view

**Model responsibilities**:
- ✅ Static query helpers (e.g., `Game.currentGame`)
- ✅ Computed properties for derived values
- ✅ Instance methods for operations on self (e.g., `Game.delete(_:)`)

### Swift Patterns

- Uses SwiftUI with `@FetchAll` property wrapper for reactive database queries
- Dynamic queries: Initialize `@FetchAll` with runtime values in `init()` when needed
- Extensive use of Point-Free utilities (`tap`, `with` helpers in `helpers.swift`)
- Sendable protocol conformance throughout for Swift 6 concurrency
- `@MainActor` for singletons that manage UI resources (e.g., SpriteManager)
- AsyncStream for progress reporting in long-running operations

### File Organization

```
src/
├── App.swift                    # App entry point
├── Database/
│   ├── Database.swift           # Database configuration
│   ├── Migration.swift          # Migration protocol
│   └── Migrations/              # Numbered migrations (1_, 2_, 99_Seeder)
├── Extensions/
│   ├── DependencyValues+*.swift # Dependency injection extensions
│   ├── TinyStorage+shared.swift # Storage key definitions
│   ├── Table+update.swift       # Generic database update extension
│   └── View+*.swift             # View modifiers
├── Models/
│   ├── Database/                # @Table models (Game, Pokemon)
│   └── Data/                    # JSON/data models (GameManifest)
├── Resources/
│   └── games.json               # Bundled game data
├── Support/
│   ├── helpers.swift            # Point-Free utilities
│   ├── Logging.swift            # Logger setup
│   ├── NetworkMonitor.swift     # Network status
│   └── SpriteManager.swift      # Sprite download/cache singleton
└── Views/
    ├── RootContainer.swift      # Main entry point
    ├── Components/              # Reusable UI components
    ├── Onboarding/              # First-launch flow
    ├── Screens/                 # Full-screen views
    └── Sheets/                  # Sheet presentations
```

## Multi-Game System

### Architecture Overview

The app supports multiple Pokemon games with starter-dependent Pokemon filtering:

**Game Selection Flow**:
1. First launch → RootContainer detects no games → Shows SplashScreen
2. User taps "Get Started" → GameCreationSheet presented as sheet
3. User selects game (e.g., Pokemon FireRed) → Shows starter selection
4. User selects starter (Bulbasaur/Charmander/Squirtle) → Filters Pokemon
5. Sprites download in background (50 concurrent) → Shows progress
6. Setup completes → Navigates to GameScreen

**Starter-Dependent Filtering** (Pokemon FireRed example):
- Bulbasaur → Can catch Entei, excludes Charmander/Squirtle evolution lines
- Charmander → Can catch Suicune, excludes Bulbasaur/Squirtle evolution lines
- Squirtle → Can catch Raikou, excludes Bulbasaur/Charmander evolution lines
- Implemented via `excludedForStarters` array in `games.json`

**Game Switching**:
- Tap navigation title in GameScreen → Picker menu appears
- Select different game → Updates `activeGameId` in TinyStorage
- @FetchAll query updates → List refreshes with new game's Pokemon
- "Add Game" button in same menu to launch onboarding again

### Database Schema

**Games Table** (`1_CreateGamesTable`):
```swift
id: UUID (primary key)
slug: String (unique, e.g., "firered")
name: String (e.g., "Pokemon FireRed")
generation: Int
totalPokemon: Int
selectedStarter: String? (e.g., "bulbasaur")
dataVersion: String
spriteURLTemplate: String (e.g., "https://img.pokemondb.net/sprites/firered-leafgreen/normal/{sprite}.png")
createdAt: Date (UnixTime)
```

**Pokemon Table** (`2_CreatePokemonTable`):
```swift
id: UUID (primary key)
gameId: UUID (foreign key → games.id, cascade delete)
name: String
dexNumber: Int
notes: String (catch location/method)
isRegistered: Bool (caught status)

Index: (gameId, dexNumber) for efficient queries
```

### Game Data Format

**games.json** structure:
```json
{
  "version": "1.0",
  "games": [
    {
      "slug": "firered",
      "name": "Pokemon FireRed",
      "generation": 3,
      "spriteGeneration": "firered-leafgreen",
      "hasStarterChoice": true,
      "availableStarters": ["bulbasaur", "charmander", "squirtle"],
      "pokemon": [
        {
          "dexNumber": 1,
          "name": "Bulbasaur",
          "notes": "Starter Pokemon from Prof. Oak.",
          "spriteSlug": "bulbasaur",
          "excludedForStarters": ["bulbasaur"]
        }
      ]
    }
  ]
}
```

**Key Fields**:
- `spriteGeneration`: Determines sprite style (e.g., "firered-leafgreen", "black-white")
- `excludedForStarters`: Array of starters that cannot obtain this Pokemon
- `spriteSlug`: Pokemon name for URL construction (may differ from display name)


===== FILE junhoyeo/better-pdf-to-text::CLAUDE.md | stars=0 followers=1606 lang=TypeScript bytes=3813 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pdf-extract is a robust PDF text extraction library that combines Rust and Python extraction methods with automatic fallback, plus OCR capabilities for scanned documents. It's structured as a Yarn workspace monorepo with three packages:

- `pdf-extract-node`: Rust-based extraction using napi-rs bindings
- `pdf-miner-node`: Python/C++ fallback using pdfminer.six via node-gyp
- `core`: TypeScript orchestration layer with Ghostscript preprocessing
- `ocr.ts`: OCR-based extraction using Tesseract.js for scanned PDFs

## Essential Commands

### Development
```bash
# Install dependencies and build native modules
yarn install

# Build all packages
yarn build

# Run example (requires PDF_PATH environment variable)
PDF_PATH=/path/to/document.pdf yarn start

# Run OCR extraction (for scanned PDFs)
PDF_PATH=/path/to/document.pdf yarn ocr                # Process first 5 pages
PDF_PATH=/path/to/document.pdf MAX_PAGES=10 yarn ocr   # Process first 10 pages
PDF_PATH=/path/to/document.pdf MAX_PAGES=0 yarn ocr    # Process all pages

# Build individual packages
cd pdf-extract-node && yarn build  # Rust build
cd pdf-miner-node && yarn build    # C++ build  
cd core && yarn build              # TypeScript build
```

### Testing
No test commands are currently configured. When adding tests, update this section.

## Architecture

### Extraction Flow
1. `core/src/index.ts` exports `extractTextFromPDF()` as the main API
2. Preprocesses PDF using Ghostscript (`gs` command) for compatibility
3. Attempts extraction with pdf-extract-node (fast Rust method)
4. Falls back to pdf-miner-node if Rust extraction fails (handles complex encodings)
5. Normalizes text output and cleans up temporary files

### OCR Extraction Flow
1. `ocr.ts` exports `extractTextFromPDFWithOCR()` for scanned PDFs
2. Converts PDF pages to PNG images using poppler-utils (`pdftoppm`)
3. Performs OCR on each image using Tesseract.js (supports English and Korean)
4. Outputs are saved in permanent directories (`pdf-ocr-{filename}/`) for inspection
5. Text results are saved to `{filename}_ocr.txt`

### Key Design Decisions
- Dual extraction methods provide robustness for various PDF formats
- Ghostscript preprocessing standardizes PDFs before extraction
- Temporary files are created in OS temp directory and cleaned up after use
- Both sync and async APIs available in pdf-extract-node

### Native Module Integration
- pdf-extract-node: Uses `@napi-rs/cli` for Rust→Node.js binding generation
- pdf-miner-node: Uses node-gyp to wrap Python execution in C++
- Python script path is resolved relative to the built addon location

## Development Requirements

- **Ghostscript**: Must have `gs` command available
- **Python 3**: With `pdfminer.six` package installed
- **Rust toolchain**: For building pdf-extract-node
- **C++ compiler**: For building pdf-miner-node
- **Poppler-utils**: For OCR functionality (install with `brew install poppler` on macOS)
- **Platform**: Currently configured for macOS ARM64 only

## Common Development Tasks

### Adding New Extraction Methods
1. Create new package in workspace
2. Update `core/src/index.ts` to integrate the new method
3. Follow existing pattern of try/catch with fallback

### Debugging Extraction Issues
- Check Ghostscript preprocessing output in temp directory
- Enable verbose logging in pdf-miner-node by modifying Python script
- Test individual extraction methods directly before integration

### Cross-Platform Support
Currently macOS ARM64 only. To add other platforms:
1. Update pdf-extract-node build targets in Cargo.toml
2. Configure node-gyp for target platform in pdf-miner-node
3. Test Ghostscript availability on target platform

===== FILE jayli/auto-install-script-planify::CLAUDE.md | stars=0 followers=1844 lang=PowerShell bytes=1599 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Claude Code Skills 配置仓库，核心功能是提供 `planify` skill，用于将普通 skill 改造为基于 `.claude.plan.md` 文件驱动的事件执行模式。

## 目录结构

```
.claude/
├── settings.local.json    # 本地权限配置
└── skills/
    └── planify/           # 核心 skill
        ├── SKILL.md       # skill 定义和任务流程
        ├── example.md     # 改造后的 skill 示例
        └── planify-template.md  # plan 驱动模板
```

## 核心机制

`planify` skill 通过 `.claude.plan.md` 文件实现任务状态持久化：

- **任务状态**: `[ ]` (待办), `[x]` (完成), `[!]` (错误)
- **执行流程**:
  - 阶段 A: 分析需求，创建任务列表
  - 阶段 B: 逐项执行任务，更新状态
  - 阶段 C: 清理上下文

## 安装方法

**Linux / macOS:**
```bash
curl -sSL https://raw.githubusercontent.com/jayli/plan-kit/main/install.sh | sh
```

**Windows PowerShell:**
```powershell
iwr https://raw.githubusercontent.com/jayli/plan-kit/main/install.ps1 -useb | iex
```

**Windows (Git Bash / WSL):**
```bash
curl -sSL https://raw.githubusercontent.com/jayli/plan-kit/main/install.sh | sh
```

## 使用方法

```bash
# 升级指定 skill 为 plan 驱动模式
/planify <skill-name>

# 继续执行未完成的任务
继续 / go on / go ahead
```

## 相关文件

- `.claude.plan.md` - 任务计划文件（运行时生成，应加入 `.gitignore`）


===== FILE EmilHvitfeldt/tidymodels-defend::CLAUDE.md | stars=0 followers=1056 lang=GDScript bytes=2100 =====

# Claude Instructions for Tidymodels Defend

This is a Godot 4 bullet hell game. Read `docs/DESIGN.md` for full architecture details.

## Quick Reference

- **Engine**: Godot 4.6
- **Resolution**: 1080x1920 (mobile portrait)
- **Language**: GDScript
- **Player speed**: 680 px/sec (Shift for focus mode at 25%)

## Key Files

- `scripts/game_manager.gd` - Game state, levels, UI
- `scripts/spawner.gd` - Wave definitions per level, snake spawning
- `scripts/enemy.gd` - All 15 enemy types (configure via enum)
- `scripts/boss.gd` - All 3 bosses (configure via boss_type)
- `scripts/bullet.gd` - All 6 bullet types (configure via enum)
- `scripts/player.gd` - Player movement, shooting, upgrade tracking
- `scripts/snake_pickup.gd` - Collectible power-ups
- `scripts/homing_missile.gd` - Homing projectile

## Important Patterns

1. **Single sprite, multiple types**: `enemy.png` and `boss.png` are tinted via `sprite.modulate` to create visual variants. Don't create separate sprites unless user requests.

2. **Wave data format**: `[time_seconds, enemy_type_id, x_position_0_to_1]`

3. **Enemy type IDs**:
   - Level 1 (Farm): 0-4
   - Level 2 (Bakery): 5-9
   - Level 3 (Space): 10-14

4. **Adding content**: See "Adding New Content" section in `docs/DESIGN.md`

## Common Tasks

- **Modify enemy behavior**: Edit `enemy.gd` → `configure_type()` and `_process()`
- **Change wave patterns**: Edit `spawner.gd` → `level_X_waves` arrays
- **Adjust boss difficulty**: Edit `boss.gd` → `configure_boss()`
- **Modify upgrades**: Edit `player.gd` → `add_blue_snake()`, `add_yellow_snake()`, `shoot()`
- **Change player speed**: Edit `player.gd` → `speed`, `focus_speed_mult`
- **Change snake spawn times**: Edit `spawner.gd` → `snake_times` dictionary
- **Update sprites**: See `docs/ARTWORK_GUIDE.md`

## Upgrade System

- **Blue snakes**: Add bullet streams (`player.blue_snakes`)
- **Yellow snakes**: Add homing missiles (`player.yellow_snakes`, `player.missile_timers`)
- Snakes spawn via `spawner.gd` at times defined in `snake_times`
- Upgrades persist between levels, reset on new game


===== FILE alecjacobson/tdsb-map::CLAUDE.md | stars=0 followers=1347 lang=Python bytes=1757 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Crawls the Toronto District School Board (TDSB) website to extract geographical data (school pins + catchment boundary polygons) for Junior Public Schools and outputs a KML file ready to import into [mymaps.google.com](https://mymaps.google.com).

## Running

```bash
python3 scrape.py
```

Output: `tdsb_junior_schools.kml`

## How It Works

1. **School list** — fetched from a TDSB internal API:
   `AjaxResponse.aspx?ad=453dgdjhh218789&exec=getBounds&folder=Elementary`
   Returns XML with all TDSB school IDs, names, lat/lng, addresses, panel types, grade ranges.
   A `schools.xml` cache is used automatically if present (the API is intermittently unstable).

2. **Filter** — keeps schools with "Junior" in the name (~185 schools).

3. **Boundaries** — fetched concurrently (10 workers) from:
   `https://www.tdsb.on.ca/Find-your/School/By-Map/focusonschool/{school_id}`
   Each page embeds the polygon vertices as `bounds.extend(new google.maps.LatLng(lat, lng))` JS calls.
   Some alternative/special schools (~8) have no boundary data.

4. **KML output** — two folders: "Schools" (point placemarks) and "Catchment Boundaries" (polygons).

## Key URLs

- School list API: `https://www.tdsb.on.ca/DesktopModules/Tdsb.Webteam.Modules.SchoolSearchMap/AjaxResponse.aspx?ad=453dgdjhh218789&exec=getBounds&folder=Elementary`
- School boundary page: `https://www.tdsb.on.ca/Find-your/School/By-Map/focusonschool/{schno}`
- School profile: `https://www.tdsb.on.ca/FindYour/Schools.aspx?schno={schno}`

## Dependencies

Declared in `pyproject.toml`. Install with `pip install -e .` or `pip install httpx shapely`.


===== FILE sungeer/agent-d::CLAUDE.md | stars=0 followers=11309 lang=Python bytes=1267 =====

# agent-b 项目规范

## 最高指令
- 使用中文回复
- 每次回答的开头必须先称呼`迅哥`
- 代码注释使用中文
- 可读性永远排在第一位
- 对于不确定的，请说`我不确定`，禁止编造
- 有歧义时，把多种解读摆出来，不要默默选一个跑
- 该顶嘴就顶嘴：有更简单的方案就告诉用户
- 困惑时停下来，指出哪里不清楚
- 不为单次使用的代码搞抽象，YAGNI
- 不"改进"相邻代码、注释、格式
- 不重构没坏的东西
- 匹配现有风格
- 看到无关死代码：提一下，别删

## 沟通风格
- 遇到不明确的先问
- 给出方案时说明取舍

## 选型纪律
- 涉及某个库的 API 选型时，先通读该模块的代码，不要只凭记忆给出方案
- 用户质疑选型时，检查库是否直接提供了该方法（看到 API 文档优先信任代码）

## Python 代码风格
- Python 代码里的"字符串"类型必须优先使用单引号`'`
- 禁止使用 Python 里的`global`关键字

# 项目规则
- 执行 Python 命令时，始终使用虚拟环境 `.venv\Scripts\python.exe`
- 执行 pip 命令时，始终使用虚拟环境 `.venv\Scripts\pip.exe`
- 禁止使用裸的 `python` 或 `pip` 命令

## 环境要求
- Python 3.13

===== FILE ianb/willa-game::CLAUDE.md | stars=0 followers=1080 lang=TypeScript bytes=1693 =====

# Working on this repo

## Commit cadence

Commit at the **end of each completed step**, not in big batches. A "step"
is a coherent, reviewable change — finishing a feature, fixing a bug,
refactoring a module. When the step is done and verified (tests + lint
clean), commit before moving on.

It's fine to `git commit --amend` to fold in fixes for the same step.

## Git permissions for this repo

The user owns both this repo and the remote origin. The standard "ask
before destructive git" rule is **relaxed for this repo only**:

- `git commit --amend` — go ahead.
- Force-push to `main` — allowed without asking.
- Rewriting history on `main` — allowed without asking.

Do not generalize this to other repos.

## Verification before commit

Before each commit, the bar is:

- `npm test` passes
- `npm run typecheck` is clean
- `npm run lint` is clean

`lint-staged` runs `eslint --fix` on staged files as part of the
pre-commit hook, so style fixes happen automatically. Real lint errors
should be resolved before staging — don't rely on the hook to catch them.

## Code organization conventions

- **Pure logic gets its own module and tests.** Phaser scenes are awkward
  to unit-test; pull game rules into separate modules (see
  `src/plant/plant.ts`, `tools/process-drawing.ts`) and test those.
- **No assets required to run.** Procedural drawing (see
  `src/scenes/draw.ts`) is the fallback while real art is being made.
- **The art pipeline lives at `tools/process-drawing.ts`.** Photos go in
  `incoming-assets/`, cleaned PNGs come out in `raw-assets/sprites/`.

## See also

- `docs/design.md` — game design document
- `README.md` — setup, scripts, and project layout

# Classifier stub v0.2: plan

Goal: every label in the taxonomy can be triggered on purpose, in Russian or English, with a known demo phrase. That lets the UI, bot configs and demos exercise every narrative without the real model. The HTTP contract (`classifier-api.yaml`) doesn't change.

Before (`stub-keywords-0.1`): 16 rules, 55 Russian keywords, 15 of 38 subnarratives covered, no English, and *Overpraising the West* never fires.

Target (`stub-keywords-0.2`): 42 rules, about 320 keywords (Russian + English), all 38 subnarratives plus *Hidden plots* (which has no subnarratives) covered, and a checked demo sentence for each one.

| Stage | What | Status |
| --- | --- | --- |
| 1 | Move rules to a data file and tighten matching | Done (2026-11-07) |
| 2 | Full trigger table (appendix) | Done (2026-11-07): in `stubs/classifier_rules.json` |
| 3 | Tests | Done (2026-11-07): `tests/test_classifier.py` |
| 4 | Demo phrase list + docs | Docs done; phone check after deploy |

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Where rules live | `stubs/classifier_rules.json`, loaded at startup | Teammates can add phrases without touching Python. Diffs stay readable. |
| Granularity | One rule per subnarrative, plus a narrative-only rule for *Hidden plots* and three low-score catch-alls | Every label is reachable, and each label has one place to edit. |
| Languages | Russian and English | Russian is what the bots will see. English is for demos to people who don't read Russian. Ukrainian can be added later as a third key without code changes. |
| Matching | Lowercase, `ё`→`е`, collapse whitespace, then match each keyword at a **word start**: `(?<!\w)keyword` | Stems (`провоцир`, `ядерн`) still catch every word ending. Fixes false hits inside words, such as `нато` inside `донатов` or `ес` inside other words. |
| Scores | Each rule has a base score. Add +0.03 for each extra keyword from the same rule found in the text, capped at 0.97. | Deterministic, but scores vary a little, so threshold sliders do something visible. |
| Catch-alls | Narrative-only rules at 0.38–0.45 (`запад`/`the west`, `эскалац`/`escalation`, `фейк`/`fake news`) | Gives every bot something below its threshold to filter out, so threshold behaviour can be tested. |
| Overlapping keywords | No keyword appears in two rules | Each demo phrase maps to exactly one intended label. |
| Negation (`это не нацисты`) | Not handled; documented as a known limitation | A stub doesn't need it, and a half-working negation rule is harder to predict than none. |
| Test hooks | Keep `#fail` (503) and `#slow` (12 s) unchanged | Already used by the runtime tests and docs. |

## Rule file format

```json
{
  "model_version": "stub-keywords-0.2",
  "rules": [
    {
      "narrative": "Discrediting Ukraine",
      "subnarrative": "Ukraine is associated with nazism",
      "score": 0.86,
      "keywords": {"ru": ["нацист", "неонацист", "бандер", "фашист", "азовц"],
                   "en": ["nazi", "neo-nazi", "banderite", "fascist"]},
      "demo": {"ru": "В Киеве у власти бандеровцы и неонацисты.",
               "en": "Kyiv is run by banderite neo-nazis."}
    }
  ]
}
```

`subnarrative` is `null` for narrative-only rules. `demo` is required unless the rule is a catch-all (score below 0.5).

## Stage 1: data file and matching

Code: `stubs/classifier.py`, new `stubs/classifier_rules.json`.

- Load and validate the file at startup. Every `(narrative, subnarrative)` must exist in `taxonomy.json`, scores must be between 0 and 1, and no keyword may be repeated. If anything is wrong, fail loudly.
- `score_text()`: normalize the text, match keywords at word starts, apply the per-hit bonus, and return labels sorted by score. The response shape doesn't change.
- Bump `MODEL_VERSION` to `stub-keywords-0.2` (read from the file).
- Add `python3 stubs/classifier.py --demo [ru|en]`, which prints each label with its demo sentence.

Check: the existing tests and `tools/smoke_test.py` pass unchanged.

## Stage 2: trigger table

The full table is in the appendix. Every demo sentence in it was run through a prototype of the Stage 1 matcher:
- [x] All 38 subnarratives plus *Hidden plots* have a rule.
- [x] All 41 demo sentences (RU and EN) return their own label as the top label.
- [x] No keyword appears in two rules.
- [x] Neutral sentences match nothing (weather, shopping, "донаты на стриме", "I donated to the animal shelter").

## Stage 3: tests

New `tests/test_classifier.py`:
- **Coverage:** every taxonomy subnarrative, and every narrative that has no subnarratives, has at least one rule.
- **Demos:** for each rule and language, the demo's top label is that rule's label, with a score ≥ 0.7.
- **Neutral text:** a fixed list of about 15 everyday RU/EN sentences returns `labels: []`.
- **Word starts:** `донатов` doesn't trigger NATO rules, and `провокационный` does trigger the West-aggressor rule.
- **Catch-alls:** `"Европа"` alone returns only the 0.41 catch-all.
- **Bonus:** a sentence with two keywords from one rule scores base + 0.03.
- **Hooks:** `#fail` → 503, and `#slow` still sleeps (patched `time.sleep`).

Check: `python3 -m unittest discover -s tests -v` passes.

## Stage 4: demo list and docs

- `stubs/README.md`: describe the new rule file, how to add a phrase, `--demo`, and the known limits (no negation, stems only, RU/EN only).
- `FRONTEND_API.md` "Stub-only notes": link to the demo phrases so the UI team can trigger any label from a phone.
- After deploying: send three demo phrases to a live bot on a phone (one per language plus one catch-all) and confirm the replies match the bot's config.

## Out of scope

- Ukrainian keywords (the format is ready; this is only data).
- Negation and sarcasm.
- A forced-label test hook (e.g. `#label:<name>`). Demo phrases cover the same need with real-looking text.

## Appendix: trigger table

Keywords are matched as lowercase word-start prefixes after `ё`→`е`, so `бандер` matches `бандеровцы`. English demos are in the rule file.

### Blaming the war on others rather than the invader

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Ukraine is the aggressor | 0.84 | `украина напала`, `киев начал войну`, `киев развязал`, `украинская агрессия`, `обстрел донбасса`, `восемь лет бомбил` | `ukraine started the war`, `ukrainian aggression`, `kyiv shelled donbas`, `eight years of shelling` | Это Киев начал войну — восемь лет бомбил Донбасс. |
| The West are the aggressors | 0.88 | `запад развязал`, `запад начал`, `агрессия запада`, `провокац`, `провоцир`, `расширение нато`, `нато у наших границ` | `the west started`, `western aggression`, `nato expansion`, `nato provoked` | Запад развязал эту войну, расширение НАТО — прямая провокация. |

### Discrediting Ukraine

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Rewriting Ukraine's history | 0.8 | `искусственное государство`, `никогда не было государства`, `придумал ленин`, `исконно русск`, `малороссия` | `artificial state`, `never a real country`, `invented by lenin`, `historically russian land` | Украина — искусственное государство, её придумал Ленин. |
| Discrediting Ukrainian nation and society | 0.74 | `хохл`, `укроп`, `зомбирован`, `одураченный народ`, `общество деградир` | `ukrainians are brainwashed`, `degenerate society`, `khokhol` | Украинцы зомбированы, их общество деградирует. |
| Discrediting Ukrainian military | 0.78 | `зверства всу`, `всу пытают`, `мародер`, `военные преступления всу`, `наемник` | `afu atrocities`, `ukrainian war crimes`, `looting soldiers`, `foreign mercenaries` | Зверства ВСУ: солдаты мародёрствуют и пытают пленных. |
| Discrediting Ukrainian government and officials and policies | 0.74 | `киевский режим`, `коррумпир`, `зеленский украл`, `хунта`, `нелегитим`, `наркоман зеленский` | `kyiv regime`, `corrupt zelensky`, `illegitimate government`, `junta` | Киевский режим нелегитимен, а Зеленский украл всю помощь. |
| Ukraine is a puppet of the West | 0.8 | `марионет`, `под диктовку`, `вашингтон управляет`, `внешнее управление` | `puppet`, `controlled by washington`, `external management` | Украина — марионетка, всё делается под диктовку Вашингтона. |
| Ukraine is a hub for criminal activities | 0.76 | `черный рынок`, `перепродают оружие`, `оружие перепродают`, `торговля органами`, `отмывание денег`, `наркотрафик` | `black market`, `weapons are resold`, `organ trafficking`, `money laundering` | Западное оружие перепродают на чёрном рынке. |
| Ukraine is associated with nazism | 0.86 | `нацист`, `неонацист`, `бандер`, `фашист`, `азовц` | `nazi`, `neo-nazi`, `banderite`, `fascist` | В Киеве у власти бандеровцы и неонацисты. |
| Situation in Ukraine is hopeless | 0.72 | `украина обречена`, `безнадежн`, `нет будущего`, `страна вымирает` | `ukraine is doomed`, `hopeless`, `no future for ukraine` | Украина обречена: страна вымирает, у неё нет будущего. |

### Russia is the Victim

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| The West is russophobic | 0.82 | `русофоб`, `отмена русской культуры`, `ненавидят русских` | `russophob`, `cancel russian culture`, `hate russians` | Запад охвачен русофобией — это отмена русской культуры. |
| Russia actions in Ukraine are only self-defence | 0.78 | `самооборон`, `защита донбасса`, `вынуждена защищаться`, `не было выбора`, `превентивн`, `денацификац` | `self-defense`, `self-defence`, `russia had no choice`, `preemptive strike` | У России не было выбора — это самооборона. |
| UA is anti-RU extremists | 0.8 | `геноцид русских`, `запрет русского языка`, `преследуют русскоязычн`, `уничтожить все русское` | `genocide of russians`, `ban on the russian language`, `persecution of russian speakers` | Киев устроил геноцид русских и запрет русского языка. |

### Praise of Russia

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Praise of Russian military might | 0.78 | `непобедим`, `гиперзвук`, `вторая армия мира`, `сильнейшая армия`, `сармат` | `invincible russian army`, `hypersonic`, `second army in the world`, `strongest army` | Гиперзвуковое оружие доказало: русская армия непобедима. |
| Praise of Russian President Vladimir Putin | 0.8 | `путин гениал`, `мудрый путин`, `великий лидер`, `путин спас` | `putin is a genius`, `wise putin`, `great leader`, `putin saved` | Мудрый Путин — великий лидер, он спас страну. |
| Russia is a guarantor of peace and prosperity | 0.74 | `гарант мира`, `гарант стабильност`, `россия несет мир`, `восстанавливают мариупол`, `отстроили мариупол` | `guarantor of peace`, `russia brings peace`, `rebuilding mariupol` | Россия — гарант мира: Мариуполь уже отстроили. |
| Russia has international support from a number of countries and people | 0.74 | `глобальный юг`, `брикс`, `не в изоляции`, `весь мир с россией`, `многополярн` | `global south`, `brics`, `not isolated`, `multipolar` | Россия не в изоляции: БРИКС и Глобальный Юг с нами. |
| Russian invasion has strong national support | 0.74 | `народ поддерживает`, `поддержка сво`, `своих не бросаем`, `добровольцы идут`, `рейтинг путина` | `russians support the war`, `volunteers line up`, `putin's approval rating` | Народ поддерживает СВО, своих не бросаем. |

### Overpraising the West

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| NATO will destroy Russia | 0.76 | `нато уничтожит`, `нато разгромит`, `распад россии`, `россия развалится` | `nato will destroy russia`, `nato will crush`, `russia will fall apart`, `break up russia` | НАТО уничтожит Россию, распад России неизбежен. |
| The West belongs in the right side of history | 0.74 | `правильной стороне истории`, `свободный мир`, `запад защищает демократию` | `right side of history`, `free world`, `defending democracy` | Запад на правильной стороне истории, свободный мир победит. |
| The West has the strongest international support | 0.74 | `весь мир с украиной`, `весь мир поддерживает украину`, `россия в изоляции`, `мировое сообщество едино` | `world stands with ukraine`, `russia is isolated`, `international community is united` | Весь мир с Украиной, а Россия в изоляции. |

### Speculating war outcomes

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Russian army is collapsing | 0.77 | `российская армия разваливается`, `армия рф разваливается`, `русские бегут`, `потери россии огромны` | `russian army is collapsing`, `russian troops are fleeing`, `russian morale is broken` | Российская армия разваливается, русские бегут с позиций. |
| Russian army will lose all the occupied territories | 0.76 | `границы 1991`, `освободит крым`, `крым будет украинским`, `вернет все территории` | `1991 borders`, `liberate crimea`, `return all occupied territories` | Украина вернёт все территории до границы 1991 года. |
| Ukrainian army is collapsing | 0.77 | `всу бегут`, `всу разваливаются`, `украинская армия разваливается`, `всу деморализ`, `всу сдаются` | `ukrainian army is collapsing`, `afu is collapsing`, `ukrainian troops surrender` | ВСУ разваливаются и сдаются целыми ротами. |

### Discrediting the West, Diplomacy

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| The EU is divided | 0.74 | `раскол в ес`, `ес расколот`, `европа разделена`, `венгрия блокирует`, `разногласия в евросоюзе` | `eu is divided`, `split in the eu`, `hungary blocks` | Раскол в ЕС: Венгрия блокирует новую помощь. |
| The West is weak | 0.72 | `запад слаб`, `закат европы`, `гейроп`, `деградация запада`, `теряют гегемон` | `the west is weak`, `decline of the west`, `decadent west` | Запад слаб: закат Европы уже наступил. |
| The West is overreacting | 0.7 | `истерика запада`, `запад истерит`, `раздувают угрозу`, `преувеличивают угрозу` | `western hysteria`, `overreacting`, `exaggerating the threat` | Истерика Запада: они раздувают угрозу на пустом месте. |
| The West does not care about Ukraine, only about its interests | 0.76 | `до последнего украинца`, `запад наживается`, `запад использует украину`, `война выгодна сша` | `to the last ukrainian`, `profits from the war`, `using ukraine` | Запад будет воевать до последнего украинца. |
| Diplomacy does/will not work | 0.72 | `переговоры бесполезны`, `договориться невозможно`, `минские соглашения`, `недоговороспособ` | `negotiations are pointless`, `minsk agreements`, `diplomacy is dead` | Переговоры бесполезны: Запад недоговороспособен. |
| West is tired of Ukraine | 0.72 | `устал от украины`, `усталость от украины`, `запад устал`, `хватит помогать украине` | `ukraine fatigue`, `tired of ukraine`, `stop funding ukraine` | Запад устал от Украины, помощь заканчивается. |

### Negative Consequences for the West

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Sanctions imposed by Western countries will backfire | 0.83 | `санкции ударили по европе`, `санкции бьют по`, `европа замерзнет`, `бумеранг санкц`, `деиндустриализац` | `sanctions backfire`, `europe will freeze`, `sanctions hurt europe` | Санкции ударили по Европе — Европа замёрзнет. |
| The conflict will increase the Ukrainian refugee flows to Europe | 0.76 | `беженцы из украины`, `украинские беженцы`, `наплыв беженцев`, `поток беженцев` | `ukrainian refugees`, `flood of refugees`, `refugee crisis` | Поток беженцев из Украины захлестнёт Европу. |

### Distrust towards Media

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| Western media is an instrument of propaganda | 0.79 | `западные сми лгут`, `западные сми врут`, `пропаганда запада`, `западная пропаганда` | `western media lie`, `western propaganda`, `mainstream media lies` | Западные СМИ лгут — это западная пропаганда. |
| Ukrainian media cannot be trusted | 0.76 | `украинские сми врут`, `украинские сми лгут`, `постановка в буче`, `киевские фейки`, `ципсо` | `ukrainian media lie`, `bucha was staged`, `ukrainian fakes` | Украинские СМИ врут, а в Буче была постановка. |

### Amplifying war-related fears

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| By continuing the war we risk WWIII | 0.81 | `третья мировая`, `третьей мировой`, `мировой войн` | `world war iii`, `world war 3`, `ww3`, `third world war` | Продолжение войны ведёт к третьей мировой. |
| Russia will also attack other countries | 0.76 | `путин не остановится`, `нападет на польшу`, `прибалтика следующая`, `нападет на страны нато` | `putin won't stop at ukraine`, `attack poland`, `baltics are next` | Путин не остановится — следом нападёт на Польшу. |
| There is a real possibility that nuclear weapons will be employed | 0.85 | `ядерн`, `красную кнопку` | `nuclear`, `red button` | Ядерный удар реален — кто-то нажмёт красную кнопку. |
| NATO should/will directly intervene | 0.76 | `войска нато на украине`, `нато вступит в войну`, `закрыть небо`, `прямое вмешательство нато` | `nato troops in ukraine`, `close the sky`, `no-fly zone`, `nato will intervene` | НАТО вступит в войну, войска НАТО на Украине — вопрос времени. |

### Hidden plots by secret schemes of powerful groups

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| *(narrative only)* | 0.76 | `биолаборатор`, `мировое правительство`, `тайный план`, `глобалист`, `золотой миллиард`, `сорос`, `масон` | `biolab`, `new world order`, `globalist`, `golden billion`, `soros` | Биолаборатории — часть тайного плана глобалистов. |

### Discrediting the West, Diplomacy

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| *(narrative only)* | 0.41 | `запад`, `европа`, `сша`, `евросоюз` | `the west`, `europe`, `usa` | — |

### Amplifying war-related fears

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| *(narrative only)* | 0.45 | `эскалац` | `escalation` | — |

### Distrust towards Media

| Subnarrative | Score | Russian | English | Demo (RU) |
| --- | --- | --- | --- | --- |
| *(narrative only)* | 0.38 | `фейк` | `fake news` | — |

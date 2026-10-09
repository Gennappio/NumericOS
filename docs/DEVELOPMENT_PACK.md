# NumericOS — Development & Milestone Agent Pack

**NumericOS** è il nome del prodotto: un *agentic workbench* per ricerca computazionale con GUI scientifica, bacheca Kanban, commenti direttamente sulle porzioni di testo prodotte dagli agenti, Context Engine, osservabilità numerica e runtime per esperimenti, loop e delega multiagente. Il motore interno si chiama **NumericOS Runtime**.

Questa cartella è un **pacchetto di specifiche e istruzioni per coding agent**, non un'implementazione funzionante.

## Start here

1. Crea un repository Git vuoto ed estrai il pacchetto nella root.
2. Leggi `AGENTS.md` e `CURRENT_MILESTONE.md`.
3. Consulta `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md`, `docs/SKILL_ARCHITECTURE.md` e `docs/AGENT_ADAPTER_CONTRACT.md`.
4. Chiedi al coding agent di eseguire **un solo ticket** della milestone attiva; non autorizzare il passaggio a quella successiva senza i test di uscita.
5. Le skill minime di M1 sono già presenti in `skills/`, ma il loader/registry va sviluppato: non sono ancora installate automaticamente in Codex/Claude/Pi.

## File

| Percorso | Scopo |
| --- | --- |
| `AGENTS.md` | Visione d'insieme e invarianti di progetto |
| `CURRENT_MILESTONE.md` | Fase attiva M0; avanzare solo dopo test e revisione |
| `milestones/M0/AGENTS.md` | Fondamenta, persistenza e prima board GUI |
| `milestones/M1/AGENTS.md` | Primo provider reale, skill registry, discussioni selezionate, Kanban |
| `milestones/M2/AGENTS.md` | Knowledge items e compilazione del contesto approvato |
| `milestones/M3/AGENTS.md` | Esperimenti eseguibili, osservabilità, provenienza e validator |
| `milestones/M4/AGENTS.md` | Loop di ricerca, domain skills, skill selection e benchmark |
| `milestones/M5/AGENTS.md` | CLI/API per altri agenti, provider multipli, multiagente, HPC |
| `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md` | Blueprint aggiornato e criteri di uscita |
| `docs/SKILL_ARCHITECTURE.md` | Libreria canonica SKILL.md e installazione multiprovider |
| `docs/AGENT_ADAPTER_CONTRACT.md` | Interfacce di Codex/Claude/Pi e schema eventi |
| `skills/*/SKILL.md` | Prime tre skill scientifiche in formato Agent Skills |
| `docs/ml-autopilot-reference_SKILL.md` | Skill di riferimento originaria, conservata per provenienza |

## Decisioni rispetto al precedente piano CRR

- Rebranding dell'intero **prodotto** in NumericOS, con runtime come modulo interno.
- Comando CLI di progetto proposto: `numericos`, non `crr`.
- **Codex App Server** è l'integrazione da provare per prima in M1; Claude Agent SDK e Pi RPC sono adapter programmati, senza lock-in. Si può cambiare il primo provider solo dopo uno spike tecnico e un ADR.
- **Scientific Skill Registry già in M1**, non introdotto per la prima volta in M4. Il registry usa una sola raccolta canonica di Agent Skills e controlla l'installazione nel provider scelto.
- **M3** collega le skill a controlli numerici eseguibili; **M4** porta skill di dominio e selezione contestuale automatizzabile; **M5** supporta skill selezionate da agenti chiamanti.
- GUI, annotazione del testo, bacheca scientifica, stato e osservabilità persistenti rimangono requisiti primari.

## Prompt per il coding agent

> Read `AGENTS.md`, `CURRENT_MILESTONE.md`, `milestones/M0/AGENTS.md` and the v0.2 implementation plan. Build only the first incomplete M0 ticket, using real GUI/API persistence and appropriate tests. The product is NumericOS, and `numericos` is the proposed CLI. Do not prematurely integrate providers or skill execution in M0. Conclude with files changed, commands/tests run, known limitations and the next ticket. Do not start M1 automatically.

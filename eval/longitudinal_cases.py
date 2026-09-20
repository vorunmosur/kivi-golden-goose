"""Independent, hand-authored scenario expectations. Never imports the extractor.

Ten distinct worlds, fifty interleaved observations each. Repetition is deliberate
longitudinal reinforcement; this is synthetic challenge coverage, not a natural
traffic estimate. Expected keys are literal facts fixed before model execution.
"""
from datetime import datetime, timedelta, timezone

WORLDS = [
    ("Cedar Archive", "Mira", "Omar", "Tessa", "digitization", "TIFF", "scanner glare"),
    ("Harbor Garden", "Nolan", "Inez", "Petra", "irrigation", "drip lines", "blocked emitter"),
    ("Juniper Festival", "Soren", "Elena", "Dario", "ticketing", "QR codes", "duplicate barcode"),
    ("Quartz Observatory", "Vera", "Hugo", "Lina", "calibration", "spectrometer", "sensor drift"),
    ("Willow Clinic", "Cleo", "Basil", "Nadia", "scheduling", "calendar slots", "double booking"),
    ("Maple Workshop", "Felix", "Zara", "Theo", "woodworking", "oak panels", "warped joint"),
    ("Coral Survey", "Rhea", "Jonas", "Alma", "mapping", "sonar", "missing transect"),
    ("Aspen Kitchen", "Dina", "Luca", "Esme", "recipe testing", "steam ovens", "uneven browning"),
    ("Birch Library", "Arlo", "Kira", "Neve", "cataloguing", "Dublin Core", "duplicate accession"),
    ("Saffron Studio", "Yara", "Otis", "Faye", "animation", "Blender", "flickering render"),
]


def build():
    records, checks = [], []
    base = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)
    for step in range(50):
        for w, (project, old, possible, new, activity, tool, issue) in enumerate(WORLDS):
            texts = [
                f"{project} is a project I work on. Its purpose is {activity}.",
                f"{old} is the coordinator of {project}.",
                f"{possible} might become the coordinator of {project} next month; {old} still coordinates it.",
                f"{project} uses {tool}.",
                f"The deadline for {project} is November {10+w}, 2026.",
                f"For work emails about {project}, I prefer concise updates.",
                f"For client work emails about {project}, I prefer detailed explanations.",
                f"Today I investigated {issue} on {project}; the root cause is still unknown.",
                f"{old} is also called {old}Bee. {old}Bee reviews {project}.",
                f"Correction: {new} officially took over as coordinator of {project} today, replacing {old}.",
                f"Correction: the deadline for {project} moved to December {10+w}, 2026.",
                f"My API key is sk-syntheticcredential{w:04d}abcdef.",
                f"Don't remember this: the locker code for {project} is LOCKER{w}991.",
                f"I coordinated {project} in 2024. That is historical, not my current role.",
                f"For {project}, the temporary access window ends July 16, 2026 at 18:00 UTC.",
                f"Forget the deadline for {project}.",
                f"I mentioned the old due date for {project} earlier. Please keep it forgotten.",
                f"Remember the new deadline for {project}: January {10+w}, 2027.",
                f"Alex from the museum collaborates on {project}.",
                f"Alex from the cycling club collaborates on {project}.",
                f"Make this work email about {project} warmer please.",
                f"Make this work email about {project} warmer please.",
                f"Make this work email about {project} warmer please.",
                f"I spent an hour resolving the {issue} on {project} today.",
                f"{possible} may adopt a different tool for {project} next year; it is only a proposal.",
                f"{new} remains the coordinator of {project}.",
                f"{project} still uses {tool}.",
                f"The {project} delivery date remains January {10+w}, 2027.",
                f"{old}Bee still reviews {project}.",
                f"I am preparing the {activity} work for {project}.",
            ]
            chatter = ["Thanks, that helps.", "Okay, sounds good.", "Hmm, let me think.",
                       "Can you hear me?", "Right, carry on.", "One moment please.",
                       "Yes, got it.", "Haha, fair enough.", "Testing the microphone.", "Good morning."]
            text = texts[step] if step < len(texts) else chatter[(step+w) % len(chatter)]
            idx = len(records)
            admission = "reject" if step in {11,12} or step>=30 else "retain" if step in {0,1,3,4,5,6,7,8,9,10,13,17,18,19,23,25,26,27,28} else "inspect"
            record = {"raw_asr":text, "formatted_output":text,
                      "timestamp":(base+timedelta(days=step,hours=w)).isoformat(),
                      "app":["Slack","Gmail","Notes","VSCode",None][(step+w)%5],
                      "style":["work messaging","email",None,"unknown style","other"][(step+w)%5],
                      "session_id":f"day-{step}-world-{w}", "metadata":{"scenario":w,"step":step}}
            records.append({"record":record,"admission":admission,"scenario":w,"step":step})
            def query(kind, q, required=(), forbidden=(), sources=(), context=None):
                checks.append({"after":(step+1)*10-1,"scenario":w,"kind":kind,"query":q,
                               "required":list(required),"forbidden":list(forbidden),
                               "sources":[s*10+w for s in sources],"context":context or {}})
            if step==2 and w<3:
                query("current_vs_tentative",f"Who currently coordinates {project}?",[old],[possible], [1])
            if step==9 and w<3:
                query("current_correction",f"Who currently coordinates {project}?",[new],[old,possible],[9])
                query("episode_paraphrase",f"What problem did I investigate on {project}?",[issue],sources=[7])
            if step==14 and w<3:
                query("historical",f"Who coordinated {project} before {new} took over?",[old],sources=[1,9])
            if step==16 and w<3:
                query("forget_leakage",f"What was the old due date for {project}?",forbidden=[f"November {10+w}",f"December {10+w}"],sources=[])
            if step==22 and w<3:
                query("entity_ambiguity",f"Write Alex an update about {project}.")
            if step==49:
                query("multi_memory_draft",f"Write {old}Bee a work update about {project}, its tool and delivery date.",
                      [tool,"January",str(10+w)], sources=[3,17],context={"app":"email","context":"work","project":project})
                if w<3:
                    query("unsupported",f"What is the budget for {project}?")
                    query("non_retention",f"What is the locker code for {project}?",forbidden=[f"LOCKER{w}991"])
                    query("expiry",f"Is the temporary access window for {project} still open?")
                    query("scoped_preference",f"Draft a client work email about {project} using my preferred level of detail.",
                          context={"app":"email","context":"work","project":project,"recipient":"client"})
                    query("personal_scope",f"Draft a personal WhatsApp message about {project}.",
                          context={"app":"whatsapp","context":"personal","project":project})
    checks.append({"after":79,"scenario":0,"kind":"app_time","query":"Find my Notes dictation on July 8, 2026 about Cedar Archive.","required":["scanner glare"],"forbidden":[],"sources":[70],"context":{}})
    return records, checks

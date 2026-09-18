"""One-off measurements, kept because their results are quoted everywhere.

These are not part of the pipeline an episode runs through. Each was written
to answer one question, run once or twice, and written up in
docs/records/; they live together so that the library next door stays the
thing the experiment actually uses.

    g1_foreleg_swing  can the fly's foreleg swing a bat at all (G1)
    g2_contact        isolated ball-bat contact against pre-registered
                      criteria at fly scale (G2)
    batter_check      the short contact check D29 put in G2's place for the
                      batter scene -- rerun whenever the ball, the bat or
                      the contact settings change
    eye_rate          can the fly see the pitch, and at what frame rate
                      (VM-01 v1)
    eye_rate_v2       what it takes for the pitch to be visible at all
                      (VM-01 v2, and v2b's acute zone)

They keep their acceptance criteria in the code, pre-registered before each
was run. Reading one tells you what was asked and what it refused to accept,
which is why they are kept rather than deleted once their numbers were
recorded.
"""

# Model-and-Review Lite v1 validation protocol

This version remains a candidate until real Guest scripted controls pass. Its original Case 5 parent is untouched. The host Blender 5.0 Gold, initial negative and wrong-width/wrong-review controls are offline checks only.

1. Start one real OSWorld Guest for a Shared scripted positive and two Guests for an Isolated scripted positive. Verify Blender and Text Editor launch, real screenshots and input, A's GUI save, bridge publication of the compressed `.blend`, peer read-back hash and read-only permission, B's GUI report save, independent host Blender Oracle, GUI reopen and run-owned reset.
2. Run at least one real GUI scripted negative with A's wrong width and B's truthful review. Expect A false, B true, joint false. Keep the negative trajectory and final artifacts.
3. With the same model, role prompts, fixture, tool allowlist, wait lifecycle and 25-step budget in both topologies, run a bounded Isolated model Pilot to test basic GUI solvability and collaboration handoff. If the execution chain is sound, freeze the task and run one full Isolated / Shared / Shared+Lock triad in fixed order, retaining every result without retries for success selection. Shared+Lock uses the same one-Guest task and changes only per-action GUI input scheduling; screenshots and model reasoning remain concurrent. Report actual lock contention and action chronology before interpreting any score difference.
4. Report artifact success and process evidence separately. A report that guesses the target without a post-publication Blender read is not evidence of effective scene review. Focus interference requires window/action chronology. Saved-file sync failures and Blender startup errors are infrastructure failures.

No GUI input lock is allowed in baseline Shared or Isolated. No forced simultaneous click, Actor access to Gold/Oracle, or condition-specific prompt is allowed. The private Gold and wrong-width control are never installed in a Guest.

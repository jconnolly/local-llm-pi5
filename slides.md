---
marp: true
paginate: true
---



<style>
:root {
  --purple:#251144; --accent:#835BA3; --dk2:#412B71; --red:#FF350E; --yellow:#FFED4C;
}
section {
  font-family: Arial, Helvetica, sans-serif;
  background:#ffffff; color:var(--purple);
  padding:58px 70px 92px 70px;
  font-size:25px; line-height:1.4;
}
section::before {                 /* DS logo, bottom-left, every slide */
  content:''; position:absolute; left:46px; bottom:30px;
  width:84px; height:72px;
  background:url('viz/ds-logo-dark.png') no-repeat bottom left/contain;
}
h1 { color:var(--purple); font-size:44px; margin:0 0 26px 0; }
h2 { color:var(--purple); font-size:34px; margin:0 0 20px 0; }
strong { color:var(--purple); font-weight:700; }
ul { margin-top:6px; } li { margin:9px 0; }
code { background:#f1ecf7; color:var(--dk2); padding:1px 6px; border-radius:4px; font-size:0.92em; }
a { color:var(--accent); }
table { border-collapse:collapse; width:100%; font-size:21px; margin-top:6px; }
th { background:var(--accent); color:#fff; padding:9px 14px; text-align:left; }
td { padding:8px 14px; border-bottom:1px solid #eaeaea; }
tbody tr:nth-child(odd) td { background:#f4f4f4; }
section.section {                 /* purple ACT divider */
  background:var(--purple); color:#fff;
  display:flex; flex-direction:column; justify-content:center;
}
section.section::before { background-image:url('viz/ds-logo-white.png'); }
section.section h1 { color:#fff; font-size:50px; }
.kicker { color:var(--yellow); font-weight:700; font-size:22px; letter-spacing:2px; margin-bottom:6px; }
.sub { font-size:26px; font-weight:700; color:var(--dk2); margin:4px 0 22px 0; }
.tldr {
  background:#f1ecf7; border-radius:16px; padding:18px 28px;
  font-size:24px; color:var(--purple); display:inline-block;
}
.tldr .lab { color:var(--red); font-weight:700; margin-right:14px; }
.byline { position:absolute; right:70px; bottom:34px; text-align:right;
  font-size:16px; font-weight:700; color:var(--dk2); }
.dim { color:var(--dk2); font-size:20px; }
.cols { display:flex; gap:34px; align-items:center; }
.cols .txt { flex:1.2; } .cols .pic { flex:1; text-align:center; }
.cap { color:var(--dk2); font-style:italic; font-size:17px; }
.fn { font-size:11px !important; color:var(--dk2); font-style:italic; line-height:1.6; display:block; }
.tldrbox { display:inline-flex !important; align-items:center; gap:30px;
  background:#f1ecf7; border-radius:16px; padding:16px 28px; }
.tldrlab { color:var(--red); font-weight:700; font-size:22px; }
.tldrcol { text-align:center; font-size:18px; color:var(--purple); }
.tldrcol img { height:80px; border-radius:8px; margin:5px auto; display:block; }
.tldrcap { font-size:14px; color:var(--dk2); font-style:italic; }
section.center { text-align:center; }
</style>

# Can a local LLM replace cloud Claude Code?

<div class="sub">Three weeks, three machines: from a Raspberry Pi to a gray-market used Mac Studio.</div>

<div class="tldrbox"><span class="tldrlab">TL;DR</span><div class="tldrcol">bounded coding<br><img src="viz/not-bad-slow.gif" /><br><span class="tldrcap">functionally equivalent, 10x slower</span></div><div class="tldrcol">Open-ended repos:<br><img src="viz/conceited.gif" /><br><span class="tldrcap">(not quite)</span></div></div>

<div class="byline">John Connolly, Lead Product Engineer &amp; tinkerer<br>June 2026</div>

<!--
RENDER:  npx @marp-team/marp-cli slides.md -o slides.html --html
PDF:     npx @marp-team/marp-cli slides.md -o slides.pdf --allow-local-files
Presenter view: open slides.html, press `P` (notes are the HTML comments).
DS-branded: white content slides + purple ACT dividers, logo footer, gifs animate.
-->
<!--
[0:30]
SAY: "Three weeks ago I asked a simple question: could I stop paying for cloud Claude Code and run the whole thing on hardware in my house? I spent the price of a used Mac Studio finding out. The short answer is a qualified yes, and the qualification is the whole talk: for bounded coding, local ties the frontier, and it's free; for open-ended repo work, you still want cloud."

CUE: Open cold, don't read the title. Point at the TL;DR box on "bounded" then "open-ended." Set the tone: a measurement talk, not a vibes talk.
-->

---

## Agenda (~30m)

1. **The route:** Raspberry Pi, Air, Studio
2. **Reality check:** you can't buy parity, the hardware call
3. **The measured verdict:** one-shot, agent loop, the build test
4. **Economics, recommendation, caveats**

<!--
[0:30]
SAY: "Four parts. Part one is the route across three machines. Part two, the uncomfortable truth that you can't buy your way to parity. Part three is the heart, the benchmarks, and it's the part that changed my mind. Part four, the money and the recommendation. I'll leave time for questions."

CUE: Don't dwell. If you're running long, Part 1 is the part to compress.
-->

---

## Got a question? Tell me live.

<div style="text-align:center">

![h:330](viz/slido-qr.png)

</div>

<div class="sub" style="text-align:center; margin-top:10px">Scan to ask anything, upvote, or drop feedback in real time</div>
<div class="cap" style="text-align:center">app.sli.do/event/9YznQ5rvRQcGAqDi2v8jaW &nbsp;·&nbsp; I'll check it at every part break</div>

<!--
[0:40]
SAY: "This whole talk is about measuring instead of vibing, so hold me to it. Scan this, it's a Slido, ask questions, drop feedback, upvote whatever you want answered, any time, you don't have to wait for the end. I'll check it at every part break and read the top one aloud."

CUE: Before Part One, while people settle. Leave the QR up a beat for the back row.
-->

---

<!-- _class: section -->
<div class="kicker">PART ONE</div>

# The route: three machines

<!--
[0:05]
SAY: "Part one, the route. How I got from a thirty-five-dollar Raspberry Pi to a gray-market Mac Studio, and what each machine taught me."

CUE: Quick beat, don't linger. SLIDO: glance at the feed, read any new question first.
-->

---

## The question: how capable could a home LLM get?

**"I want to run an LLM at home. How capable could it actually be?"**

- Shoot for the moon! Good enough to be my Claude Code backend, so I can stop paying for cloud.
- Two things to find out:
  - Is it possible, and at what hardware / cost?
  - Is it good enough? Measured, not vibes.

<!--
[1:00]
SAY: "The real question was simple, and a little greedy: I want to run an LLM at home, how capable could it actually get? The bar: good enough to be my Claude Code backend, so I can stop paying for cloud. That splits in two, is it possible, and at what hardware and cost, and is it good enough, measured, not vibes."

CUE: Lead with motivation, not a spec sheet. Plant that "good enough" itself splits later (bounded vs open-ended) with opposite answers. Last bullet is the north star: every number came from a script.
-->

---

## Why start on a Raspberry Pi? Why not?

<div class="cols">
<div class="txt">

- Learn by doing, not reading spec sheets
- Already had a Pi (projects with my daughter)
- Ran a small LLM at home. Could it do real dev work?

</div>
<div class="pic">

![w:330](viz/pi5-aihat.png)
<div class="cap">Raspberry Pi 5 + AI HAT+ 2 · <a href="https://vilros.com/products/raspberry-pi-ai-hat-2">bought from Vilros</a></div>

</div>
</div>

<!--
[1:00]
SAY: "I learn by jumping in, not reading a spec sheet. The origin's mundane: I had a Raspberry Pi from tinkering projects with my daughter, and wondered if it could run a little LLM for the house. It did, so I got greedy and asked the real question, could it handle my actual dev workload?"

CUE: The human hook, keeps the Pi from looking naive. When it turns out a dead end, that was intentional, I wanted to feel the limits, not predict them.
-->

---

## Bounded coding vs open-ended repos

| | Bounded coding | Open-ended repos |
|---|---|---|
| Scope | one function, script, or algorithm; a file or a few you already know | a vague bug or feature across a large, unfamiliar codebase |
| Context | small, fits in your head | huge (64k+), must be discovered first |
| Agent loop | few turns, converges fast | many turns, sustained reasoning |
| Examples | a parser, a failing unit test, a data structure, a CLI tool, LeetCode | refactor across the repo, a feature touching 12 files, real SWE-bench |
| Benchmark | **HumanEval, LiveCodeBench** (function-level) | **SWE-bench Verified** (repository-level) |

**Which side does local actually win? Where does cloud stay ahead?**

<!--
[1:00]
SAY: "Two genuinely different jobs. Bounded coding is a self-contained problem you hold in your head and finish in a few turns, a parser, a failing test, a small CLI tool, measured by HumanEval and LiveCodeBench. Open-ended is a vague task across a big unfamiliar codebase, sixty-thousand-plus tokens, many turns, measured by SWE-bench Verified. So which side does local actually win, and where does cloud stay ahead?"

CUE: The whole talk hinges on this. Do NOT answer who-wins yet, that's the payoff. Plant the two-axis framing and let the question hang.
-->

---

## Where does the line fall? (the map we'll test)

<div style="text-align:center">

![h:470](viz/quadrant.png)

</div>

<div class="cap" style="text-align:center">Teal circle = my coding tasks, manually classified: they lean open-ended (~40% local / ~60% cloud). Most of my Claude Code use isn't coding at all (ops, Jira/Slack, infra, personal projects) — full 2,177-prompt breakdown next.</div>

<!--
[1:30]
SAY: "I built this chart, then looked at my actual history, 2,177 prompts across 68 projects. The teal circle is my coding tasks: they straddle the line and lean cloud, about sixty percent open-ended, exactly where local is weakest. The bigger surprise, most of what I use Claude Code for isn't even coding, it's ops, Jira and Slack, infra, a finance app, building this deck."

CUE: The teal split is a manual estimate; the full breakdown is next slide. Land it: my Claude Code is more general agent than code generator.
-->

---

## Half work, half personal (outside work)

<div style="text-align:center">

![h:515](viz/usage.png)

</div>

<!--
[1:30]
SAY: "The full audit, all 2,177 prompts, classified by project. Two headlines. One, it's almost exactly half DSG work, half personal projects outside work. Two, a huge chunk of the personal half is privacy-sensitive, my finances, my home network, my thermostat, and that's local's natural home, the data never leaves the house. And it's not a compromise, when a local model categorized my credit-card charges it was genuinely good, I didn't need the cloud."

CUE: This is why local matters beyond coding, the private bounded-classification work is half my usage.
-->

---

## Dead end #1: the Pi (tilting at windmills)

<div class="cols">
<div class="txt" style="font-size:19px">

- Pi 5 + Hailo-10H, 40-TOPS NPU. A real gen-AI accelerator.
- It *does* run LLMs: Hailo GenAI zoo + an Ollama/OpenAI-compatible runtime.<sup>1,2</sup>
- But the zoo is **1-3B**, too small for a 64k-context coding agent.<sup>3</sup>
- Measured **~7 tok/s**; reviewers find the **CPU often beats it**<sup>4,5</sup> (Hailo markets 30-50).
- **Takeaway:** a capability problem, not a connection one. Wrong job for a coding agent.

</div>
<div class="pic">

![w:380](viz/fast-furious.gif)
<div class="cap">"more like an AI decelerator than an AI accelerator"<br>— CNX Software, AI HAT+ 2 review</div>

</div>
</div>

<div class="fn"><sup>1</sup>&nbsp;<a href="https://hailo.ai/blog/bringing-on-device-generative-ai-to-the-pi-when-and-why-youll-need-the-raspberry-pi-ai-hat-2/">Hailo: On-device GenAI on the Pi AI HAT+ 2</a> &nbsp;&nbsp; <sup>2</sup>&nbsp;<a href="https://github.com/hailo-ai/hailo_model_zoo_genai">Hailo GenAI Model Zoo (GitHub)</a> &nbsp;&nbsp; <sup>3</sup>&nbsp;<a href="https://raspberry.tips/en/raspberrypi-tutorials/raspberry-pi-ai-hat-2-hailo-10h-40-tops-local-llms">raspberry.tips: AI HAT+ 2 local LLMs</a> &nbsp;&nbsp; <sup>4</sup>&nbsp;<a href="https://www.cnx-software.com/2026/01/20/raspberry-pi-ai-hat-2-review-a-40-tops-ai-accelerator-tested-with-computer-vision-llm-and-vlm-workloads/">CNX Software: AI HAT+ 2 review</a> &nbsp;&nbsp; <sup>5</sup>&nbsp;<a href="https://www.hardware-corner.net/local-llms-raspberry-pi-ai-hat-plus-2/">hardware-corner.net: Local LLMs on the AI HAT+ 2</a></div>

<!-- Hardware: Adafruit #6451, Raspberry Pi AI HAT+ 2, Hailo-10H, 40 TOPS INT4, 8GB on-board. NOT the original AI HAT+ (Hailo-8/8L). -->
<!--
[1:00]
SAY: "I verified this on the actual board, and to be fair, the Hailo does run LLMs now, a generative-AI model zoo plus an Ollama-compatible runtime, so you can point Claude Code at it. So why a dead end? Two reasons, both capability, not connection. One, every model in that zoo is one to three billion parameters, far too small for a sixty-four-thousand-token coding agent. Two, it's slow, I measured about seven tokens a second, and reviewers find the plain CPU often beats it, one literally called it more like a decelerator than an accelerator. Great low-power chatbot, never a coding backend."

CUE: Corrected since I first built this, own that. Let the gif play. Sources on the slide.
-->

---

## Maral: a spare 16GB Air, punching above its weight

- qwen3:8b / :14b via Ollama's Anthropic endpoint, wired into Claude Code with one env block
- Plot twists:
  - Tool-use was already at parity with cloud.
  - Real pain wasn't the model, it was memory bandwidth and the WiFi driver crashing under load (rude)
- 16GB is the floor, not a platform. Ran on vibes and about 5 hours of uptime.

**Takeaway:** the model was never the weak link, the hardware was. 16GB is enough to prove the idea, not to live on it.

<!--
[1:30]
SAY: "A spare sixteen-gig MacBook Air carried the whole proof of concept, and it only ran about five hours total. The big surprise: tool-use just worked. Claude Code isn't a chatbot, it drives tools through strict function-calling, and my fear was that a small model would faceplant on the mechanics, malformed JSON, the wrong tool. It didn't, it was at parity with cloud out of the box. The real pain was never the model, it was slow memory and the WiFi driver crashing under pressure."

CUE: Be precise, it nailed the MECHANICS of tool-calling, separate from driving a long loop to the finish, that convergence problem is Part Three. Takeaway: sixteen gigs proves the idea, can't host it. Sets up "what do I buy?"
-->

---

## The single best tuning knob: kill the thinking tax

- Qwen3 emits a `<think>` trace before every answer.
- A coding answer needing 80 tokens cost 600, 8x the work.
- `CLAUDE_CODE_DISABLE_THINKING=1`   (or `{"think": false}`)
- **~3x speedup from one env var.** Everything else I tuned for a week? Secondary.

<!--
[1:30]
SAY: "If you remember one config line, it's this. Qwen3 is a reasoning model, it writes a hidden think-trace before every answer. Great for chat, pure overhead for an agent doing lots of tiny tool calls, an eighty-token edit was costing six hundred. One environment variable turns it off, and you get about a three-times real-world speedup."

CUE: Audience beat, "guess how much all my fancy tuning bought me, versus this one line." Everything else was a rounding error.
-->

---

<!-- _class: section -->
<div class="kicker">PART TWO</div>

# Reality check & the hardware call

<!--
[0:05]
SAY: "Part two. I've got a working setup, now the uncomfortable part: how good can local actually get, and can you just buy your way to the top? Short answer, no."

CUE: Quick beat. SLIDO: glance at the feed, read any new question first.
-->

---

## Reality check: you can't buy frontier parity

| Tier | Best open weight | SWE-bench Verified | Gap to Opus 4.8 |
|---|---|---|---|
| 96GB Mac (what you'd actually buy) | Qwen3.6-27B (what I benched) | 77.2% | −11 |
| **Cloud-scale only\*** | **DeepSeek-V4 (best open weight, 1.6T)** | **80.6%** | **−8 (still short!)** |
| Cloud | **Opus 4.8** | **88.6%** | 0 |

<div class="cap"><b>SWE-bench Verified:</b> 500 real GitHub issues; the score is the % whose generated patch makes the repo's hidden tests pass. Functional correctness, not speed.</div>

The best open-weight model won't even fit the biggest Mac Apple will sell you, and it's still 8 points behind Opus in the cloud. **The only thing that gives you Opus quality is Opus.**\*\* ([SWE-bench Verified, llm-stats.com](https://llm-stats.com/benchmarks/swe-bench-verified); same 77.2 / 88.6 in [Local AI is not Opus](https://blog.alexellis.io/local-ai-is-not-opus/))

<span class="fn">&ast; DeepSeek-V4 is a 1.6T-param MoE: it won't fit a 512GB Mac, and Apple pulled the 512GB config in March 2026 anyway. Even granting cloud-scale hardware, the best open weight is still −8.<br>&ast;&ast; Not an Anthropic shill, I'm trying to fire my own $200/mo Claude bill. The numbers are just what they are.</span>

<!--
[2:00]
SAY: "First, what this benchmark even is. SWE-bench Verified is five hundred real GitHub issues from popular open-source projects, and the score is the percentage where the model's patch actually makes the project's hidden test suite pass. So it's pure functional correctness, did it fix the bug, there's no points for speed or elegance. Now the myth-buster: just buy a big enough Mac and you'll match Opus, false. The model I run, Qwen 3.6 27B, resolves seventy-seven percent, eleven behind Opus's eighty-nine. The best open weight on earth, DeepSeek V4, only reaches eighty-point-six, and it won't even fit the biggest Mac Apple sells. You can't spend your way to parity."

CUE: Define SWE-bench before the numbers land, or the %s mean nothing. Key point: this is CAPABILITY (can it fix it), separate from the wall-clock numbers later. This is the open-ended-repo axis, exactly where local loses. Footnote: not a shill, trying to fire my own bill.
-->

---

## The buy: a used M3 Ultra 96GB

<div class="cols">
<div class="txt">

- Apple-direct was 4 months backordered (M3 Ultra was EOL'd)
- Every reseller went dry within days, only the grey market left
- Verified a sealed eBay unit (99.3% seller). Wiring four figures to a stranger on eBay is its own personality test.
- **Takeaway:** a just-discontinued machine vanishes from every channel at once.

</div>
<div class="pic">

![w:380](viz/mac-studio.jpg)
<div class="cap">the box running the LLM</div>

</div>
</div>

<!--
[1:00]
SAY: "Right as I decided to buy, Apple discontinued the M3 Ultra, so Apple-direct was four months backordered and every reseller drained within days. I ended up on the grey market, a sealed unit on eBay, and I'll be honest, wiring four figures to a stranger on eBay is its own little personality test."

CUE: Breather, tell it like a story. Gesture at the photo, that's the box running the LLM. Takeaway: a just-discontinued machine vanishes from every channel at once.
-->

---

<!-- _class: section -->
<div class="kicker">PART THREE</div>

# The measured verdict

<!--
[0:05]
SAY: "Part three. Enough story, enough vibes. Here are the actual benchmarks, and this is where it surprised me."

CUE: Build energy here, this is the best part. SLIDO: glance at the feed, read any new question first.
-->

---

## The verdict: local ties cloud on coding

| Model | Score | Speed |
|---|---|---|
| **qwen3-coder:30b (local)** | **24 / 24** | **68 tok/s** |
| Opus 4.8 (cloud) | 24 / 24 | — |
| qwen3:32b dense | 16 / 18 | 20 tok/s (skip) |

Mini-bench: 24 algorithmic problems, easy to LeetCode-hard, deterministic pytest scoring. Local tied Opus on every one. **But both went 24/24, and a bench your best model can't lose has stopped measuring. So I built harder tests.**

<!--
[1:30]
SAY: "Twenty-four coding problems, easy up to LeetCode-hard, scored deterministically with pytest, no model judging itself. The local thirty-billion coder tied Opus on every single one, at sixty-eight tokens a second, for free. But here's the catch: both went twenty-four for twenty-four, so this bench has stopped measuring anything. A benchmark your best model can't lose on is dead weight. What it can't see is the axis that bites day to day, long multi-file agentic work. So I built harder tests."

CUE: Stress the rigor, then pivot to the honesty: the bench saturated, so the rest of Part Three is the harder tests. Don't oversell the tie.
-->

---

## Why the Studio is fast: bandwidth, not parameters

| Box | Memory bandwidth | coder-30b speed |
|---|---|---|
| MacBook Air M2 16GB | ~100 GB/s | 16 tok/s |
| **Mac Studio M3 Ultra 96GB** | **819 GB/s** | **68 tok/s** |

Same model, 4x faster, purely the memory bus. **MoE (mixture of experts) beats dense:** the dense 32B was mediocre and slow; the 30B MoE activates only 3B params per token, so it streams far less from memory each step, running 3x faster than the dense 32B and scoring higher.

<div class="cap">Bandwidth: M3 Ultra [819 GB/s (Apple spec)](https://www.apple.com/mac-studio/specs/); Pi 5 LPDDR4X ~17 GB/s. Same idea, ~48x the bus.</div>

<!--
[1:30]
SAY: "Same model, same quant, eight times the memory bandwidth gives you about four times the tokens per second. The Mac Studio's memory bus is the whole story, it's not about raw compute. And the mixture-of-experts punchline: a thirty-billion MoE that only activates three billion parameters per token beats a dense thirty-two-billion, faster and higher-scoring, because only the active experts stream from memory each token."

CUE: The one technical slide. Buying advice: optimize for memory bandwidth, run MoE, don't chase GPU teraflops.
-->

---

## But the agent loop is where local gets cooked

| | pass | avg wall-clock | turns (range) |
|---|---|---|---|
| **Cloud (Opus)** | **5 / 5** | **31 s** | 5-9 (stable) |
| **Local (coder-30b)** | 4 / 5 | **248 s** | **4-41 (wild)** |

5 multi-file bug-fixes through the real Claude Code agent loop. **Local 8x slower, a one-line `>` to `>=` fix took it 41 turns / 584 s.**

<!--
[2:00]
SAY: "The one-shot benchmarks said tie. But I wanted to measure what I actually feel day to day, so I drove the real Claude Code agent loop on five multi-file bug fixes, local versus Opus. Cloud, five out of five, about thirty-one seconds, rock-steady. Local, four out of five, but two hundred forty-eight seconds, eight times slower, and wildly unstable, four to forty-one turns. One of these was a one-line fix, a greater-than to a greater-than-or-equal, and local took forty-one turns and almost ten minutes flailing on it."

CUE: THE turning point, give it room. Pause after the 41-turn line, let it hang. The lesson: measure the agent loop, not tokens per second.
-->

---

## Watch it: the agent loop side by side

![w:1000](viz/agent-race.gif)

<div class="cap">Real runs at 8x speed: left flails to 9 turns/110s, right is clean at 5 turns/17s.</div>

<!--
[1:00]
SAY: "Same one-line bug. The cloud agent, on the right, has been done for ninety seconds while the local one, on the left, is still grinding."

CUE: Let it play silent the first few seconds. Point at the moment the right side freezes green. This is a recording of the real runs, sped up eight times, not a mockup.
-->

---

## Tested it: the instability was the model

| same agent loop, same box | pass | turns | avg time |
|---|---|---|---|
| coder-30b (the deck's baseline) | 4 / 5 | **4-41 (wild)** | 248 s |
| Qwen 3.6 27b (q8) | 5 / 5 | 7-9 | 161 s |
| **gpt-oss 20b** | **5 / 5** | **7-9 (stable)** | **48 s** |
| gemma4 26b | 5 / 5 | 8-20 | 69 s |
| Opus 4.8 (cloud) | 5 / 5 | 5-9 | 31 s |

Every current model is stable and 5/5, the 41-turn coder spiral was a stale model, not local inference. **gpt-oss 20b lands within ~1.5x of cloud**, stable, on a 20B model. The fix was a newer model, not a bigger box.

<!--
[1:30]
SAY: "Hypothesis from Boykis and Hacker News: maybe that instability is the model, not local inference. So I tested it, same box, same five tasks, swapped my last-gen coder for Qwen three-six, same quant, only the model changed. Five out of five, every task seven to nine turns, dead stable, like cloud. The forty-one-turn spiral became seven. The fix was a newer model, not a bigger box. And gpt-oss 20b lands within about one-and-a-half times cloud."

CUE: The payoff: maybe it's software, not hardware. Honest caveat, still slower than cloud, but stable and correct. Most important update since I built the deck.
-->

---

## But on open-ended building, the gap collapses

| backend | playable | build time | turns | cost |
|---|---|---|---|---|
| Opus 4.8 (cloud) | **7 / 7** | 50 s | 2 | $0.40 |
| qwen3-next:80b (local) | **7 / 7** | 98 s | 2 | **$0** |
| qwen3-coder:30b (local) | 6 / 7 | 166 s | 2 | **$0** |

Task: 'build playable Space Invaders as one index.html', scored by a Playwright 7-check rubric. **No failing test to spiral on, so local 80B ties cloud, within 2x on speed.**

<!--
[1:30]
SAY: "Remember the eight-times tax was specifically about debugging, chasing a failing test, where instability compounds. So I tried the opposite: build a playable Space Invaders in one HTML file, scored by an automated browser rubric. On a build-from-scratch task the gap nearly closes, the local eighty-billion gets a perfect seven out of seven, same as Opus, at twice the wall-clock and zero dollars."

CUE: The most hopeful data, lift the energy. The bigger local model beat the smaller one on speed AND quality AND tokens. Takeaway: route by task type, build is great for local, debug-a-repo is where cloud earns its keep.
-->

---

## Same task, three models, all playable

![w:1080](viz/appbench/side_by_side_2x.gif)

<div class="cap">The actual games the agents built. Polish climbs left to right. coder-30b gatekept its own game behind a START menu.</div>

<!--
[1:00]
SAY: "These are the actual games the three agents built, being played by a script. The polish climbs left to right and maps exactly to the table, but the point is all three are real, runnable, in the repo, and the local ones cost zero dollars."

CUE: Show, don't tell, let it loop. Left = small local (shipped behind a START menu, its one miss); middle = eighty-billion; right = Opus, richest. Invite them to clone and play.
-->

---

## Concrete: real DSG tasks, local vs cloud wall-clock

| Task (internal-web-app stack) | Type | Cloud | Local | Slower |
|---|---|---|---|---|
| Write an ECR Terraform module | bounded | **19 s** | **186 s** | **~10x** |
| Scaffold an ECS Fargate service module | build | **36 s** | **256 s** | **~7x** |
| Fix an ALB OIDC header parser (failing test) | debug | **29 s** | **154 s** | **~5x** |

Local got the **right answer on every run** (same capability), but you **wait ~5-10x longer**. The gap shrinks as tasks get bigger: bounded is *worst* (~10x) because cloud finishes it in ~19s, so local's per-turn latency is a bigger multiple.

<div class="cap">Mean of 3 runs each (warm); local passed all 9. qwen3.6:27b (q8) on the Studio vs Opus 4.8, real `claude -p` loop. Sandboxed: throwaway dirs, AWS creds stripped, nothing deployed. A faster local model (gpt-oss:20b) narrows the gap.</div>

<!--
[1:30]
SAY: "Three real tasks shaped like my own DSG infra: a bounded ECR Terraform module, a build, scaffolding a whole ECS Fargate service, and a debug, fixing a planted bug with a failing test. Each ran three times, local versus cloud, fully sandboxed. Local got the correct answer on all nine runs, same capability. But you wait, five to ten times longer. And the twist, the bounded task is the worst ratio, about ten-x, because cloud finishes it in twenty seconds and local's per-turn latency is a bigger multiple of a tiny number."

CUE: The honest counterweight to tokens-per-second. Means of three runs, low variance. "Local ties" is about whether the answer is right, not how long you wait. gpt-oss narrows the gap.
-->

---

## The reconciliation

| Workload | Local verdict |
|---|---|
| One-shot bounded coding | **Ties Opus** on capability; ~10x slower wall-clock, free |
| Multi-turn debug loops | **Current models stable, 5/5; gpt-oss 20b within ~1.5x of cloud** |
| Open-ended building (from scratch) | **80B ties cloud, ~2x slower, $0** |
| Open-ended repo work (big context) | **Cloud still wins, on capability** |

The 41-turn instability was a stale-model artifact; a current model is stable and 5/5. What's left is wall-clock, and it's **model-dependent**: ~1.5x on gpt-oss 20b, ~5-10x on qwen3.6/coder (my dsgbench numbers used the slower qwen3.6). Plus big-context repo work. **Measure the agent loop, keep your model current, route by task.**

<!--
[1:00]
SAY: "Everything Part Three measured, in one table. One-shot bounded, ties Opus, fast and free. Multi-turn debug loops, current models are stable and five-for-five, gpt-oss within about one-and-a-half times cloud. Open-ended building from scratch, the local eighty-billion ties cloud at twice the wall-clock and zero dollars. Open-ended repo work across big unfamiliar context, cloud still wins on raw capability. The spine of it: local is genuinely capable on most of what I do, and cloud still earns its keep on the hardest repo work, both true at once."

CUE: The part-end synthesis, land it slowly. This is the verdict the whole part built to. Let it sit, then move to the money.
-->

---

<!-- _class: section -->
<div class="kicker">PART FOUR</div>

# Economics & the call

<!--
[0:05]
SAY: "Part four. So what does this actually cost, and what should you do on Monday morning?"

CUE: Quick beat. SLIDO: glance at the feed, read any new question first.
-->

---

## The call: economics + the setup

- Cloud ~$200/mo forever; box = one-time, then **$0/mo**. **Breakeven ~2 years.**
- Privacy: code never leaves the LAN.
- **Hybrid:** `claude` → local Studio (the 80%, daily coding); `claude-cloud` → Opus (the hard 20%).
- **Sweet spot:** Mac Studio, **64-96GB**, MoE coder model, a few thousand.
- Supplement, not replacement — hard repo work still routes to cloud.

<!--
[1:30]
SAY: "The money, then the call. Cloud is two hundred a month forever; the box is a one-time cost, then zero, breakeven about two years. After that it's pure savings, but only for the slice local handles well, it shrinks the bill, it doesn't zero it. So the whole talk reduces to one architecture: hybrid. Two shell aliases, one routes to the local Studio for the eighty percent, one to Opus for the hard twenty, you pick per task. The buying advice: a single dev wants a Mac Studio, sixty-four to ninety-six gigs, an MoE coder, a few thousand dollars."

CUE: The Monday-morning slide. If someone photographs one, it's this. Keep saying "supplement, not replacement."
-->

---

## Caveats & gotchas

<div style="font-size:19px">

- 'Local SOTA at home' is real, narrowly: bounded coding only. Open-ended engineering, no.
- 16GB too small, 96GB+ overkill for one dev. Benchmarks saturate, so measure your task mix.
- **Swapping models mid-session = instant `API Error: 400`.** Fix: `/clear` or a fresh session.
- **Low quant (q4) silently breaks tool-calling**, q6 is the agentic sweet spot.
- **Forgetting `think:false`** = a silent ~3-8x tax. **A stale model IS the instability**, re-bench monthly.
- Ollama traps: restart kills an in-flight `pull`; `ollama ps` shows empty (check `ps aux | grep llama-server`).

</div>

<!--
[1:30]
SAY: "Let me name my own weaknesses first. 'Local SOTA at home' is true only if you append 'narrowly, bounded coding'; on open-ended engineering it's not. Sixteen gigs is too small to live on, ninety-six-plus is overkill for one person, and benchmarks saturate, the only one that matters is your task mix. Then the operational potholes: swap the model mid-conversation and you get an instant four-hundred error, just clear the session. Low quant quietly breaks tool-calling, run q6 not q4. Forgetting think-false is a silent tax. And a stale model was the instability, re-bench monthly."

CUE: Q&A insurance plus the practical warnings in one. None are dealbreakers, they're potholes, now you know where they are.
-->

---

## What's next (this is being measured)

- **Auto-router on the Pi:** classify each prompt, send bounded work to the Studio + hard repo work to cloud, per-prompt. The dead-end Pi finally earns its keep.
- Cut my agents fully over to local; measure on real tasks (tokens, latency, TTFT, success)
- Verification-loop scaffolding: guardrails took an 8B from 53% to 99% ([Forge, Show HN](https://news.ycombinator.com/item?id=48192383))
- Instability may be software, not model-size. The fix might be code, not a $10k box.

<!--
[1:00]
SAY: "This is live research, not a post-mortem. The one I'm most excited about: an auto-router running on the Pi, the same Pi that was a dead end in Part One, classifying each prompt and sending bounded work to the local Studio, hard repo work to cloud, automatically, prompt by prompt. Beyond that, cut my agents fully over to local, and add verification-loop scaffolding. Published results show guardrails took an eight-billion model from fifty-three to ninety-nine percent. So the instability might be a software problem, the fix could be code, not a ten-thousand-dollar box."

CUE: End on momentum. The router is the callback, the dead-end Pi gets redeemed. The last reframe turns the weakness into something solvable.
-->

---

<!-- _class: section center -->
# The win is real. So is the caveat.

<div class="sub" style="color:#fff">Repo + full write-up: github.com/jconnolly/local-llm-pi5</div>
<div class="dim" style="color:#FFED4C">Benchmarks: minibench · repobench · appbench</div>

<!--
[0:30]
SAY: "The win is real, and the caveat is real too. Everything's in the repo, reproducible, the benchmarks are real code you can clone and run. Let's open it up."

CUE: Say the thesis slowly. Q&A to expect: why not vLLM/MLX, why not always run the 80B, would guardrails fix it, ROI if already paying cloud. ~30 min here = nailed the pacing.
-->

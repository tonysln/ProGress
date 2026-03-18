"""
Generate synthetic 2-voice training phrases for blues, jazz, and rock.
Bass plays chord roots; soprano traces chord tones by smooth voice-leading.
All output is in C (no transposition needed by the model).
"""
import os, random
from phrase_stitching.RN_analysis import COMMON_ROMAN_NUMERALS_C
from phrase_stitching.preprocess import _SEMI_TO_CLASS, _nodes_to_nxer, write_graph

_NOTE_SEMI = {
  "C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11,
  "C#":1,"D#":3,"F#":6,"G#":8,"A#":10,
  "Db":1,"Eb":3,"E-":3,"Gb":6,"G-":6,"Ab":8,"A-":8,"Bb":10,"B-":10,
}

def _closest(prev_semi, tone_names):
  """Pick the tone name with the smallest semitone distance from prev_semi."""
  def dist(name):
    d = abs(_NOTE_SEMI[name] - prev_semi) % 12
    return min(d, 12 - d)
  return min(tone_names, key=dist)

def _gen_nodes(rn_sequence, beat_ql=1.0, ts_num=4, ts_den=4):
  """
  rn_sequence: list of RN strings, one per beat.
  Returns nodes list [(abs_offset_ql, voice_idx, semitone, dur_ql)].
  Bass plays root on each chord change; soprano traces tones beat by beat.
  """
  soprano_prev = None
  soprano_segs = []  # (onset, semi, dur) — will be merged
  bass_segs    = []

  prev_rn = None
  prev_bass_onset = 0.0
  prev_bass_semi  = None

  for beat_idx, rn in enumerate(rn_sequence):
    abs_off = beat_idx * beat_ql
    tones   = COMMON_ROMAN_NUMERALS_C[rn]
    root    = _NOTE_SEMI[tones[0]]

    # Soprano: pick closest chord tone different from previous (forces motion)
    if soprano_prev is None:
      s_name = tones[min(2, len(tones) - 1)]  # start on the 5th
    else:
      other = [t for t in tones if _NOTE_SEMI[t] != soprano_prev] or tones
      s_name = _closest(soprano_prev, other)
    s_semi = _NOTE_SEMI[s_name]

    # Merge consecutive same-semi soprano beats
    if soprano_segs and soprano_segs[-1][1] == s_semi:
      soprano_segs[-1][2] += beat_ql
    else:
      soprano_segs.append([abs_off, s_semi, beat_ql])
    soprano_prev = s_semi

    # Bass: new node only when chord changes
    if rn != prev_rn:
      if prev_bass_semi is not None:
        bass_segs.append((prev_bass_onset, prev_bass_semi, abs_off - prev_bass_onset))
      prev_rn        = rn
      prev_bass_onset = abs_off
      prev_bass_semi  = root

  # Close final notes
  end = len(rn_sequence) * beat_ql
  if soprano_segs:
    soprano_segs[-1][2] = end - soprano_segs[-1][0]  # extend last to phrase end
  if prev_bass_semi is not None:
    bass_segs.append((prev_bass_onset, prev_bass_semi, end - prev_bass_onset))

  nodes = [(o, 0, s, d) for o, s, d in soprano_segs] + \
          [(o, 1, s, d) for o, s, d in bass_segs]
  nodes.sort(key=lambda x: (x[0], x[1]))
  return nodes

def _phrases_to_file(progressions, out_path, beat_ql=1.0, ts_num=4, ts_den=4):
  with open(out_path, 'w') as f:
    for i, prog in enumerate(progressions):
      nodes = _gen_nodes(prog, beat_ql, ts_num, ts_den)
      N, X, E, R = _nodes_to_nxer(nodes, ts_num, ts_den)
      write_graph(f, N, X, E, R, label=f"synthetic_{i}")

# ---------------------------------------------------------------------------
# Blues: 12-bar I7-IV7-V7 in C, one chord per measure (4 beats each)
# Produces 3 separate 4-bar phrases to match the stitching phrase unit.
# ---------------------------------------------------------------------------
_BLUES_SEGS = [
  ["I7"]*4 + ["I7"]*4 + ["I7"]*4 + ["I7"]*4,    # bars 1-4
  ["IV7"]*4 + ["IV7"]*4 + ["I7"]*4 + ["I7"]*4,   # bars 5-8
  ["V"]*4 + ["IV7"]*4 + ["I7"]*4 + ["V"]*4,      # bars 9-12
]

def gen_blues(output_dir, n_phrases=100):
  os.makedirs(output_dir, exist_ok=True)
  phrases_per_file, file_idx, buf = 100, 1, []
  for _ in range(n_phrases):
    seg = random.choice(_BLUES_SEGS)
    buf.append(seg)
    if len(buf) >= phrases_per_file:
      _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
      file_idx += 1; buf = []
  if buf:
    _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
  print(f"Wrote {n_phrases} blues phrases to {output_dir}")

# ---------------------------------------------------------------------------
# Jazz: ii7-V7-Imaj7 and variations, 4 bars, one chord per bar
# ---------------------------------------------------------------------------
_JAZZ_PROGRESSIONS = [
  ["ii7"]*4 + ["V"]*4 + ["Imaj7"]*4 + ["Imaj7"]*4,
  ["Imaj7"]*4 + ["ii7"]*4 + ["V"]*4 + ["Imaj7"]*4,
  ["IVmaj7"]*4 + ["ii7"]*4 + ["V"]*4 + ["Imaj7"]*4,
  ["ii7"]*4 + ["ii7"]*4 + ["V"]*4 + ["V"]*4,
  ["Imaj7"]*4 + ["IVmaj7"]*4 + ["ii7"]*4 + ["V"]*4,
]

def gen_jazz(output_dir, n_phrases=100):
  os.makedirs(output_dir, exist_ok=True)
  phrases_per_file, file_idx, buf = 100, 1, []
  for _ in range(n_phrases):
    buf.append(random.choice(_JAZZ_PROGRESSIONS))
    if len(buf) >= phrases_per_file:
      _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
      file_idx += 1; buf = []
  if buf:
    _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
  print(f"Wrote {n_phrases} jazz phrases to {output_dir}")

# ---------------------------------------------------------------------------
# Rock: I-V-vi-IV and common variants, 4 bars
# ---------------------------------------------------------------------------
_ROCK_PROGRESSIONS = [
  ["I"]*4 + ["V"]*4 + ["vi"]*4 + ["IV"]*4,
  ["I"]*4 + ["IV"]*4 + ["V"]*4 + ["I"]*4,
  ["vi"]*4 + ["IV"]*4 + ["I"]*4 + ["V"]*4,
  ["I"]*4 + ["V"]*4 + ["IV"]*4 + ["I"]*4,
  ["I"]*4 + ["IV"]*4 + ["I"]*4 + ["V"]*4,
]

def gen_rock(output_dir, n_phrases=100):
  os.makedirs(output_dir, exist_ok=True)
  phrases_per_file, file_idx, buf = 100, 1, []
  for _ in range(n_phrases):
    buf.append(random.choice(_ROCK_PROGRESSIONS))
    if len(buf) >= phrases_per_file:
      _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
      file_idx += 1; buf = []
  if buf:
    _phrases_to_file(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
  print(f"Wrote {n_phrases} rock phrases to {output_dir}")

if __name__ == "__main__":
  gen_blues("data/blues/processed/")
  gen_jazz("data/jazz/processed/")
  gen_rock("data/rock/processed/")

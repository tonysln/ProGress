from music21 import converter, note, pitch as m21pitch, interval as m21interval

# (18-class vocabulary relative to C)
# Derived from rule_guidance.SCALE_DEGREES + SCALE_DEGREE_TO_C
_SEMI_TO_CLASS = {0:2, 1:4, 2:7, 3:10, 4:11, 5:14, 6:16, 7:12, 8:8, 9:15, 10:6, 11:9}

def _metric_class(abs_ql, ts_num, ts_den):
  if ts_num % 3 == 0 and ts_num > 3:
    beat_ql = 3.0 * (4.0 / ts_den)
    bpm = ts_num // 3
  else:
    beat_ql = 4.0 / ts_den
    bpm = ts_num
  beat = int(round(abs_ql / beat_ql))
  bim = beat % bpm
  m = beat // bpm
  if bpm == 4:
    if bim == 0: return m % 2
    if bim == 2: return 2
    return 3
  return min(bim, 5)

def _active_note(flat_notes, target_ql):
  """Note sounding at target_ql in a list of music21 notes/rests (sequential)."""
  curr = 0.0
  for n in flat_notes:
    if curr <= target_ql < curr + n.quarterLength - 1e-9:
      return n if isinstance(n, note.Note) else None
    curr += n.quarterLength
  return None

def _nodes_to_nxer(nodes, ts_num=4, ts_den=4):
  """
  nodes: [(abs_offset_ql, voice_idx, semitone_0_11, dur_ql), ...]
          voice_idx: 0=soprano/treble, 1=bass
  Returns (N, X, E, R).
  """
  N = len(nodes)
  if N == 0: raise ValueError("No notes")

  max_onset = max(x[0] for x in nodes) or 1.0
  X = [_SEMI_TO_CLASS[s] for _, _, s, _ in nodes]

  R = []
  for abs_off, v, _, dur in nodes:
    mc = [0.0] * 6
    mc[_metric_class(abs_off, ts_num, ts_den)] = 1.0
    R.append(mc + [dur / 2.0, abs_off / max_onset,
                   1.0 if v == 0 else 0.0, float(v), 1.0 if v == 0 else 0.0])

  treble = [(i, off, dur) for i, (off, v, _, dur) in enumerate(nodes) if v == 0]
  bass   = [(i, off, dur) for i, (off, v, _, dur) in enumerate(nodes) if v == 1]

  def nxt(lst, idx):
    pos = next((p for p, (i, _, _) in enumerate(lst) if i == idx), None)
    return lst[pos + 1][0] if pos is not None and pos + 1 < len(lst) else None

  def prv(lst, idx):
    pos = next((p for p, (i, _, _) in enumerate(lst) if i == idx), None)
    return lst[pos - 1][0] if pos is not None and pos > 0 else None

  E = [[0] * N for _ in range(N)]
  for i, (off_i, vi, _, dur_i) in enumerate(nodes):
    lst_i = treble if vi == 0 else bass
    lst_o = bass   if vi == 0 else treble
    end_i = off_i + dur_i
    fi, bi = (3, 4) if vi == 0 else (1, 2)

    ni, pi = nxt(lst_i, i), prv(lst_i, i)
    if ni is not None: E[i][ni] = fi
    if pi is not None: E[i][pi] = bi

    for j, off_j, dur_j in lst_o:
      if   abs(off_j - off_i) < 1e-9:               E[i][j] = 5
      elif off_i < off_j < end_i - 1e-9:            E[i][j] = 8
      elif abs(off_j - end_i) < 1e-9:               E[i][j] = 6
      elif abs(off_j + dur_j - off_i) < 1e-9:       E[i][j] = 7

  return N, X, E, R

def score_to_graph(score):
  """
  Convert a 2-voice music21 Score to (N, X, E, R).

  Transposes to C, then samples each voice at every beat position.
  Consecutive beats with the same pitch are merged into one node.
  Parts[0] = soprano/melody (voice 0), parts[-1] = bass (voice 1).
  """
  key_obj = score.analyze('key')
  if key_obj.tonic.pitchClass != 0:
    transp = m21interval.Interval(key_obj.tonic, m21pitch.Pitch('C'))
    score = score.transpose(transp)

  ts = score.recurse().getElementsByClass('TimeSignature').first()
  ts_num = ts.numerator  if ts else 4
  ts_den = ts.denominator if ts else 4
  beat_ql = 3.0 * (4.0 / ts_den) if (ts_num % 3 == 0 and ts_num > 3) else 4.0 / ts_den

  flat_s = list(score.parts[0].flatten().notesAndRests)
  flat_b = list(score.parts[-1].flatten().notesAndRests)
  total  = max(sum(n.quarterLength for n in flat_s), sum(n.quarterLength for n in flat_b))
  beats  = [round(i * beat_ql, 5) for i in range(int(total / beat_ql) + 1)]

  nodes = []
  for v, flat in enumerate([flat_s, flat_b]):
    prev_semi, prev_onset = None, None
    for beat in beats:
      n = _active_note(flat, beat)
      semi = int(n.pitch.ps) % 12 if n else None
      if semi != prev_semi:
        if prev_semi is not None:
          nodes.append((prev_onset, v, prev_semi, beat - prev_onset))
        prev_semi  = semi
        prev_onset = beat if semi is not None else None
    if prev_semi is not None:
      nodes.append((prev_onset, v, prev_semi, beats[-1] + beat_ql - prev_onset))

  nodes.sort(key=lambda x: (x[0], x[1]))
  return _nodes_to_nxer(nodes, ts_num, ts_den)

def write_graph(f, N, X, E, R, label=""):
  f.write(f"N={N}\n")
  f.write("X: \n")
  f.write(" ".join(str(x) for x in X) + " \n")
  f.write("E: \n")
  for row in E:
    f.write(" ".join(str(e) for e in row) + " \n")
  f.write("R: \n")
  for row in R:
    f.write(" ".join(str(v) for v in row) + " \n")
  if label:
    f.write(label + "\n")
  f.write("\n")

def musicxml_to_graph_file(xml_path, out_path):
  score = converter.parse(xml_path)
  N, X, E, R = score_to_graph(score)
  with open(out_path, "w") as f:
    write_graph(f, N, X, E, R, label=xml_path)

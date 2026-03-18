import os, copy
from music21 import corpus, stream
from phrase_stitching.preprocess import score_to_graph, write_graph

def _two_voice_segment(soprano_part, bass_part, start_measure, num_measures):
  """Return a 2-part Score from [start_measure, start_measure+num_measures)."""
  seg = stream.Score()
  for src in [soprano_part, bass_part]:
    p = stream.Part()
    measures = list(src.getElementsByClass('Measure'))
    for m in measures[start_measure : start_measure + num_measures]:
      for n in m.notesAndRests:
        p.append(copy.deepcopy(n))
    seg.append(p)
  return seg

def _write_phrases(phrases, out_path):
  with open(out_path, 'w') as f:
    for label, (N, X, E, R) in phrases:
      write_graph(f, N, X, E, R, label=label)

def extract_mozart(output_dir, segment_measures=4):
  """Extract soprano+bass from Mozart string quartets (violin I + cello)."""
  os.makedirs(output_dir, exist_ok=True)
  graphs_per_file, file_idx, buf = 100, 1, []

  for p in corpus.search('mozart', 'composer'):
    try:
      s = corpus.parse(p)
      if len(s.parts) < 2:
        continue
      ts = s.recurse().getElementsByClass('TimeSignature').first()
      if not ts:
        continue
      melody, bass = s.parts[0], s.parts[-1]
      measures = list(melody.getElementsByClass('Measure'))
      start = 1 if len(measures) > 1 and measures[0].barDuration.quarterLength < ts.barDuration.quarterLength else 0
      i = start
      while i + segment_measures <= len(measures):
        seg = _two_voice_segment(melody, bass, i, segment_measures)
        try:
          N, X, E, R = score_to_graph(seg)
          if N < 6: raise ValueError("too sparse")
          label = f"{p.sourcePath}_m{i}"
          buf.append((label, (N, X, E, R)))
          if len(buf) >= graphs_per_file:
            _write_phrases(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
            file_idx += 1
            buf = []
        except Exception:
          pass
        i += segment_measures
    except Exception:
      pass

  if buf:
    _write_phrases(buf, os.path.join(output_dir, f"graphs_{file_idx}.txt"))
  print(f"Wrote {(file_idx - 1) * graphs_per_file + len(buf)} phrases to {output_dir}")

if __name__ == "__main__":
  extract_mozart("data/mozart/processed/")

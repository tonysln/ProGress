import copy
import pickle
import random
from collections import defaultdict
from pprint import pprint
from music21 import stream, tempo, meter
from music21.stream import Part, Score
from phrase_stitching.RN_analysis import analyze_entire_phrase, get_vertical_pairs, InvalidAnalysisException, check_illegal_harmonics_on_integer_beats, check_bad_counterpoint, check_bad_mode_mixture
from phrase_stitching.write_inner_voices import write_inner_voices

# Key = new tonic relative to previous phrase,
# Value = harmonies that may start a new phrase
POSSIBLE_STARTS_ENDING_FROM_TONIC = {
  "I": ["I", "ii", "iii", "IV", "V", "vi", "viio"],  # C -> C
  "ii": ["VII", "III", "i", "I"],  # C -> d
  "V": ["IV", "V", "ii", "viio", "iio", "iv"],  # C -> G
  "IV": ["V", "I", "vi"],  # C -> F
  "vi": ["III", "iv", "VI", "iio", "IV", "I"],  # C -> a (IV/I added for rock)
  "iii": ["VI", "iio", "iv", "V", "viio"],  # C -> e
  "i": ["i", "iio", "III", "iv", "v", "V", "VI", "VII", "viio"],  # c -> c
  "v": ["iv", "V", "viio", "iio"],  # c -> g
  "iv": ["v", "V", "iv", "iio"],  # c -> f
  "VI": ["iii", "IV", "vi", "ii"],  # c -> Ab
  "III": ["vi", "ii", "IV", "V", "viio"],  # c -> Eb
  # 7th chord entries
  "I7":    ["I7", "ii7", "IV7", "V", "I", "ii", "IV", "viio"],  # blues tonic
  "IV7":   ["V", "I7", "I", "vi", "ii7"],                       # blues subdominant
  "ii7":   ["V", "I7", "Imaj7", "I"],                           # jazz pre-dominant
  "Imaj7": ["Imaj7", "ii7", "IVmaj7", "I", "ii", "IV", "V", "vi"],  # jazz tonic
  "IVmaj7":["V", "Imaj7", "I", "vi", "ii7"],                   # jazz subdominant
}

# Each config describes a 4-phrase structure:
#   beginning_end_key: which end-key pool to draw the opening phrase from
#   phrases: (progression_key, required_end_key, transpose_semitones)
STRUCTURE_CONFIGS = [
    {  # I -> V -> I
        "beginning_end_key": "I",
        "phrases": [("V", "I", -5), ("I", "I", -5), ("IV", "I", 0)],
    },
    {  # i -> III -> V -> i
        "beginning_end_key": "i",
        "phrases": [("III", "I", 3), ("iii", "i", 7), ("IV", "i", 0)],
    },
    {  # I -> IV -> V -> I
        "beginning_end_key": "I",
        "phrases": [("IV", "I", 5), ("ii", "i", 7), ("IV", "I", 0)],
    },
    {  # i -> VI -> iv -> i
        "beginning_end_key": "i",
        "phrases": [("VI", "I", -4), ("vi", "i", -7), ("V", "i", 0)],
    },
    {  # i -> III -> iv -> i
        "beginning_end_key": "i",
        "phrases": [("III", "I", 3), ("ii", "i", 5), ("V", "i", 0)],
    },
    {  # Blues: I7 -> IV7 -> I7 -> V
        "beginning_end_key": "I7",
        "phrases": [("I7", "IV7", 0), ("IV7", "I7", 0), ("I7", "V", 0)],
    },
    {  # Jazz: Imaj7 -> ii7 -> V -> Imaj7
        "beginning_end_key": "Imaj7",
        "phrases": [("Imaj7", "ii7", 0), ("ii7", "V", 0), ("V", "Imaj7", 0)],
    },
    {  # Rock: I -> V -> vi -> I
        "beginning_end_key": "I",
        "phrases": [("I", "V", 7), ("V", "vi", 0), ("vi", "I", 0)],
    },
]

def extend_last_note_to_fill_measure(score, analysis):
  """
  Extends the last note in each part to complete the final measure up to the full measure length.
  Assumes 4/4 time unless another time signature is specified in the part.
  """
  for part in score.parts:
    ts = part.recurse().getElementsByClass(meter.TimeSignature).first()
    measure_length_quarters = ts.barDuration.quarterLength if ts else 4.0

    last_note = None
    for n in part.recurse().notesAndRests: last_note = n

    if last_note is None: continue  # skip empty parts

    last_measure = last_note.getContextByClass('Measure')
    if last_measure is None: continue

    # Total duration of the last measure
    total_duration = sum(n.duration.quarterLength for n in last_measure.notesAndRests)

    remaining_duration = measure_length_quarters - total_duration

    if remaining_duration > 0 and last_note.isNote:
      last_note.duration.quarterLength += remaining_duration
      for _ in range(int(remaining_duration)):
        analysis.append(analysis[-1])

  return score, analysis

def combine_two_scores(score1, score2):
  """Combine two music21 scores by preserving measure structure"""
  combined_score = Score()

  # Get tempo and time signature from first score
  tempos = score1.recurse().getElementsByClass(tempo.MetronomeMark)
  first_tempo = copy.deepcopy(tempos[0]) if tempos else None

  time_sigs = score1.recurse().getElementsByClass('TimeSignature')
  time_sig = time_sigs[0] if time_sigs else None

  for part1, part2 in zip(score1.parts, score2.parts):
    combined_part = Part()

    # Add score-level elements to the first measure of the combined part
    if first_tempo: combined_part.insert(0, copy.deepcopy(first_tempo))
    if time_sig: combined_part.insert(0, copy.deepcopy(time_sig))

    # Copy all measures from part1
    measures1 = part1.getElementsByClass(stream.Measure)
    for measure in measures1:
      combined_part.append(copy.deepcopy(measure))

    # Copy all measures from part2, but adjust their measure numbers
    measures2 = part2.getElementsByClass(stream.Measure)
    last_measure_num = len(measures1)

    for i, measure in enumerate(measures2):
      measure_copy = copy.deepcopy(measure)
      measure_copy.number = last_measure_num + i + 1
      combined_part.append(measure_copy)

    # Remove trailing empty measures
    combined_part = remove_trailing_empty_measures(combined_part)
    combined_score.append(combined_part)
  return combined_score

def remove_trailing_empty_measures(part):
  """Remove only trailing empty measures while preserving measure structure"""
  measures = part.getElementsByClass(stream.Measure)
  if not measures: return part

  # Find the last measure with actual content
  last_content_index = -1
  for i, measure in enumerate(measures):
    if measure.notesAndRests: last_content_index = i

  # No measures with content, return as is
  if last_content_index == -1: return part

  # If there are trailing empty measures, remove them
  if last_content_index < len(measures) - 1:
    # Create new part with non-measure elements
    new_part = Part()

    # Copy non-measure elements (like clefs, key signatures, etc.)
    for element in part:
      if not isinstance(element, stream.Measure):
        new_part.append(copy.deepcopy(element))

    # Copy only measures up to the last one with content
    for i in range(last_content_index + 1):
      new_part.append(copy.deepcopy(measures[i]))
    return new_part
  return part

def transpose_score(score, semitones):
  transposed_score = copy.deepcopy(score)
  for n in transposed_score.recurse().notes:
    n.transpose(semitones, inPlace=True)
  return transposed_score

def _sample_candidates(progression_key, required_end_key, score_analysis_starts, score_analysis_ends):
  possible_starts = POSSIBLE_STARTS_ENDING_FROM_TONIC[progression_key]
  return [
    score for start in possible_starts for score in score_analysis_starts[start]
    if score in score_analysis_ends[required_end_key]
  ]

def stitch(score_analysis_starts, score_analysis_ends, score_analysis, config):
  phrases = [None] * (len(config["phrases"]) + 1)

  while len(set(id(p) for p in phrases)) != len(phrases):
    print("Sampling possibilities...")
    phrases[0] = random.choice(score_analysis_ends[config["beginning_end_key"]])
    for i, (progression_key, required_end_key, _) in enumerate(config["phrases"]):
      candidates = _sample_candidates(progression_key, required_end_key, score_analysis_starts, score_analysis_ends)
      phrases[i + 1] = random.choice(candidates)

  analyses = []
  for i in range(len(phrases)):
    phrases[i], analysis = extend_last_note_to_fill_measure(phrases[i], score_analysis[phrases[i]])
    analyses.append(analysis)
    write_inner_voices(phrases[i], analysis)

  for i, (_, _, semitones) in enumerate(config["phrases"]):
    if semitones:
      phrases[i + 1] = transpose_score(phrases[i + 1], semitones)

  combined = phrases[0]
  for phrase in phrases[1:]:
    combined = combine_two_scores(combined, phrase)
  return combined

def get_structure():
  return random.choice(STRUCTURE_CONFIGS)

def get_organized_phrases():
  score_analyses = {}
  score_analysis_starts = defaultdict(list)
  score_analysis_ends = defaultdict(list)
  for j in [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13]:
    for i in range(1, 101):
      try:
        score, analysis = analyze_entire_phrase(f"phrase_stitching/diffusion_output/output_graphs_{j}/output_graph_{i}.xml")
        check_illegal_harmonics_on_integer_beats(score)
        check_bad_mode_mixture(score)
        check_bad_counterpoint(score)
        # print(analysis)
        score_analyses[score] = analysis
        score_analysis_starts[analysis[0]].append(score)
        score_analysis_ends[analysis[-1]].append(score)
      except (InvalidAnalysisException, FileNotFoundError) as e: continue
  return score_analysis_starts, score_analysis_ends, score_analyses

def main():
  score_analysis_starts, score_analysis_ends, score_analyses = get_organized_phrases()
  config = get_structure()
  return stitch(score_analysis_starts, score_analysis_ends, score_analyses, config)

if __name__ == "__main__":
  main()

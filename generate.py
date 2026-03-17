from phrase_stitching.stitch import get_organized_phrases, get_structure, stitch

def main():
  score_analysis_starts, score_analysis_ends, score_analyses = get_organized_phrases()
  structure_function = get_structure()
  score = stitch(score_analysis_starts, score_analysis_ends, score_analyses, structure_function)
  fname = score.write('musicxml', fp='generated.musicxml')
  print(f'Saved to {fname}')

if __name__ == "__main__":
  main()
  
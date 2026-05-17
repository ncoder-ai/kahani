#!/usr/bin/env bash
# Download the curated subset of voice references from
# https://github.com/OwenTyme/voice-zero — the LibriVox-sourced reference
# samples I cross-checked against published "best LibriVox narrator" lists.
#
# Files are FLAC; VibeVoice (and Qwen3-TTS, Chatterbox, IndexTTS) all read
# FLAC natively via torchaudio/soundfile — no conversion required.
#
# Usage:
#   ./download_curated_voices.sh [target_directory]
# If no directory is given, downloads to ./curated_voices in the cwd.
#
# Skips files that already exist (idempotent — safe to re-run).
# Exits with non-zero status if any download fails after retries.

set -euo pipefail

TARGET="${1:-./curated_voices}"
BASE_URL="https://raw.githubusercontent.com/OwenTyme/voice-zero/main/voices"

mkdir -p "$TARGET"
echo "Downloading curated voices into: $TARGET"
echo

# Format: <filename> | <reader> | <accent / notes>
# Each line is one file. The shell `read` loop below splits on `|`.
VOICES=(
    # ---- Female (prolific, top-tier LibriVox) ----
    "mil_nicholson.flac|Mil Nicholson|English — definitive Dickens reader (Oliver Twist, Bleak House)"
    "karen_savage.flac|Karen Savage|American — repeatedly cited as one of LibriVox's best"
    "karen_savage2.flac|Karen Savage|English RP — same narrator, alt accent"
    "cori_samuel.flac|Cori Samuel|English — reader ID 92 (founder-era), Black Beauty"
    "ruth_golding.flac|Ruth Golding|English RP — LibriVox staff pick"
    "kara_shallenberg.flac|Kara Shallenberg|American (SoCal) — reader ID 19, founder-era"
    "kristen_mcquillin.flac|Kristen McQuillin|American — reader ID 89, Call of the Wild"
    "annie_coleman_rothenberg.flac|Annie Coleman Rothenberg|American — reader ID 30, very early"
    "j_m_smallheer.flac|J. M. Smallheer|American — Wollstonecraft, classic-fiction strength"

    # ---- Kristin Hughes (5 emotion variants — uniquely valuable) ----
    "kristin_hughes.flac|Kristin Hughes|American (Iowa) — reader ID 28, founder-era, default"
    "kristin_hughes-angry.flac|Kristin Hughes|American (Iowa) — angry delivery"
    "kristin_hughes-expressive.flac|Kristin Hughes|American (Iowa) — expressive delivery"
    "kristin_hughes-poetic.flac|Kristin Hughes|American (Iowa) — poetic delivery"
    "kristin_hughes-sad.flac|Kristin Hughes|American (Iowa) — sad delivery"

    # ---- Male (prolific, top-tier LibriVox) ----
    "phil_chenevert.flac|Phil Chenevert|American — most prolific LibriVox reader (1000+ books)"
    "mark_f_smith.flac|Mark F. Smith|American — reader ID 204, 86+ books, 30M+ downloads"
    "mark_nelson.flac|Mark Nelson|American — reader ID 251, sci-fi/adventure veteran"
    "david_wales.flac|David Wales|American — Galsworthy, prolific older-male voice"
    "david_jaquay.flac|David Jaquay|American — reader ID 55, founder-era, Little Women"
    "david_jaquay-english.flac|David Jaquay|English — same narrator, Sherlock-Holmes accent"
    "peter_yearsley.flac|Peter Yearsley|English (London/SE) — reader ID 167, founder-era"
    "kent_f.flac|Kent F.|American — reader ID 594, Tale of Two Cities"

    # ---- Distinctive accents (rare references) ----
    "padraig_o%27hiceadha.flac|Padraig O'hIceadha|Irish — native speaker (default)"
    "padraig_o%27hiceadha-lyrical.flac|Padraig O'hIceadha|Irish — lyrical variant"
    "andy.flac|Andy|Scottish — Voltaire's Zadig"
    "ian_skillen.flac|Ian Skillen|Scottish — reader ID 1230, full novel-length"
    "graeme_dunlop.flac|Graeme Dunlop|Australian — reader ID 4172"
    "lizzie_driver.flac|Lizzie Driver|English — reader ID 684, Olaudah Equiano narrative"
)

total=${#VOICES[@]}
downloaded=0
skipped=0
failed=0

for entry in "${VOICES[@]}"; do
    IFS='|' read -r url_name reader notes <<< "$entry"
    # Save with the URL-decoded filename (apostrophes → literal `'`)
    save_name="${url_name//%27/\'}"
    dest="$TARGET/$save_name"

    if [[ -f "$dest" ]]; then
        echo "  ✓ skip   $save_name (already present)"
        skipped=$((skipped + 1))
        continue
    fi

    printf "  ⬇  fetch  %-45s  [%s, %s]\n" "$save_name" "$reader" "$notes"
    if curl -fsSL --retry 3 --retry-delay 2 -o "$dest" "$BASE_URL/$url_name"; then
        downloaded=$((downloaded + 1))
    else
        echo "    ✗ FAILED: $url_name"
        rm -f "$dest"
        failed=$((failed + 1))
    fi
done

echo
echo "Done. Downloaded: $downloaded   Skipped: $skipped   Failed: $failed   Total: $total"

if [[ $failed -gt 0 ]]; then
    exit 1
fi

# Brief sanity check: verify each file is a real FLAC by checking its
# magic bytes (`fLaC` at offset 0).
echo
echo "Verifying FLAC magic bytes..."
bad=0
for entry in "${VOICES[@]}"; do
    IFS='|' read -r url_name _ _ <<< "$entry"
    save_name="${url_name//%27/\'}"
    f="$TARGET/$save_name"
    [[ -f "$f" ]] || continue
    if [[ $(head -c 4 "$f" 2>/dev/null) != "fLaC" ]]; then
        echo "  ✗ NOT VALID FLAC: $save_name"
        bad=$((bad + 1))
    fi
done
if [[ $bad -eq 0 ]]; then
    echo "All files have valid FLAC magic bytes."
else
    echo "WARNING: $bad files failed FLAC validation — may be HTML error pages."
    exit 1
fi

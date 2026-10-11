// C testbench for tile_engine: replays golden vector sets (tools/dump_golden.py, docs/contracts.md section 8) and
// compares scores, gate, changed and frame_count exactly. Returns non-zero on any mismatch or missing set.
//
// BW_GOLDEN_DIR  vector root (default: testdata/golden)
// BW_GOLDEN_SETS space-separated set names (default: synthetic)
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "tile_engine.h"

static const int N_PIX = IMG_W * IMG_H;
static ap_uint<32> frame[N_PIX];
static ap_uint<8> scores[N_TILES];

static bool read_file(const std::string &path, std::vector<unsigned char> &buf, size_t size) {
    FILE *f = fopen(path.c_str(), "rb");
    if (!f) return false;
    buf.resize(size);
    const size_t n = fread(buf.data(), 1, size, f);
    fclose(f);
    return n == size;
}

static std::string frame_path(const std::string &dir, const char *kind, int i) {
    char name[32];
    snprintf(name, sizeof name, "/%s_%04d.bin", kind, i);
    return dir + name;
}

// Returns the number of mismatches (frames that could not be read count as one each).
static long run_set(const std::string &dir) {
    std::map<std::string, long> p;
    FILE *f = fopen((dir + "/params.txt").c_str(), "r");
    if (!f) {
        printf("FAIL %s: no params.txt\n", dir.c_str());
        return 1;
    }
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char key[64];
        long v;
        if (line[0] != '#' && sscanf(line, "%63s %ld", key, &v) == 2) p[key] = v;
    }
    fclose(f);

    struct Row { int frame, reset, update, gate, changed; };
    std::vector<Row> rows;
    f = fopen((dir + "/expect.txt").c_str(), "r");
    if (!f) {
        printf("FAIL %s: no expect.txt\n", dir.c_str());
        return 1;
    }
    while (fgets(line, sizeof line, f)) {
        Row r;
        if (line[0] != '#' && sscanf(line, "%d %d %d %d %d", &r.frame, &r.reset, &r.update, &r.gate, &r.changed) == 5)
            rows.push_back(r);
    }
    fclose(f);
    if (p["IMG_W"] != IMG_W || p["IMG_H"] != IMG_H || p["TILE"] != TILE || rows.empty()) {
        printf("FAIL %s: geometry or expect.txt does not match this core\n", dir.c_str());
        return 1;
    }

    long errors = 0, printed = 0, tile_diffs = 0;
    unsigned since_reset = 0;
    std::vector<unsigned char> buf;
    for (const Row &row : rows) {
        if (!read_file(frame_path(dir, "frame", row.frame), buf, 4 * (size_t)N_PIX)) {
            printf("FAIL %s: cannot read frame %d\n", dir.c_str(), row.frame);
            return errors + 1;
        }
        for (int i = 0; i < N_PIX; i++)
            frame[i] = buf[4 * i] | (buf[4 * i + 1] << 8) | (buf[4 * i + 2] << 16) | ((unsigned)buf[4 * i + 3] << 24);

        ap_uint<1> gate;
        ap_uint<12> changed;
        ap_uint<32> count;
        tile_engine(frame, scores, row.reset, row.update, p["K_SLOW"], p["K_FAST"], p["W_EDGE"], p["W_GREY"],
                    p["SCORE_SHIFT"], p["T_FLAG"], p["SAT_MAX"], p["SAT_TOL"], p["T_GLOBAL"], p["GATE_TILES"], &gate,
                    &changed, &count);
        since_reset = row.reset ? 1 : since_reset + 1;

        if (!read_file(frame_path(dir, "scores", row.frame), buf, N_TILES)) {
            printf("FAIL %s: cannot read scores %d\n", dir.c_str(), row.frame);
            return errors + 1;
        }
        long frame_diffs = 0;
        for (int i = 0; i < N_TILES; i++) {
            if (scores[i] == buf[i]) continue;
            frame_diffs++;
            if (printed++ < 10)
                printf("  mismatch frame %d tile_row %d tile_col %d expected %d got %d\n", row.frame, i / TILES_X,
                       i % TILES_X, (int)buf[i], (int)scores[i]);
        }
        tile_diffs += frame_diffs;
        const bool ok_gate = (int)gate == row.gate, ok_changed = (int)changed == row.changed;
        const bool ok_count = count == since_reset;
        if (!ok_gate || !ok_changed || !ok_count) {
            if (printed++ < 10)
                printf("  mismatch frame %d gate %d/%d changed %d/%d frame_count %u/%u (expected/got)\n", row.frame,
                       row.gate, (int)gate, row.changed, (int)changed, since_reset, (unsigned)count);
        }
        if (frame_diffs || !ok_gate || !ok_changed || !ok_count) errors++;
    }
    printf("%s %s: %zu frames, %ld tile scores, %ld frames with a mismatch, %ld score mismatches\n",
           errors ? "FAIL" : "PASS", dir.c_str(), rows.size(), (long)rows.size() * N_TILES, errors, tile_diffs);
    return errors;
}

int main() {
    const char *root = getenv("BW_GOLDEN_DIR");
    const char *sets = getenv("BW_GOLDEN_SETS");
    std::string base = root ? root : "testdata/golden";
    std::istringstream names(sets ? sets : "synthetic");
    std::string name;
    long errors = 0;
    int n_sets = 0;
    while (names >> name) {
        errors += run_set(base + "/" + name);
        n_sets++;
    }
    printf("%s: %d vector set(s), %ld failing frame(s)\n", errors ? "TB FAIL" : "TB PASS", n_sets, errors);
    return errors ? 1 : 0;
}

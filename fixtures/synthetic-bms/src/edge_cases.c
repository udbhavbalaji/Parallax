static int duplicate(void) { return 1; }
static int recurse(int n) { return n ? recurse(n - 1) : 0; }
int use_duplicate_a(void) { return duplicate() + recurse(2); }
extern int unavailable(void);
int call_unavailable(void) { return unavailable(); }
int call_indirect(int (*fn)(void)) { return fn(); }

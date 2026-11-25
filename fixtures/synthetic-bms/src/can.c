#include "bms.h"

static int encode_status(void) {
    return fault_flags ? 0 : 1;
}

void report_can(void) {
    (void)encode_status();
}

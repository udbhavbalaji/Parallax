#include "bms.h"

static int state_ready(void) {
    return fault_flags == 0;
}

void update_state(void) {
    if (state_ready()) {
        report_can();
    }
}

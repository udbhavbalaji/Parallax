#include "bms.h"

volatile unsigned fault_flags = 0;

static int read_cell_sample(void) {
    return 3700;
}

int check_cell_voltage(int millivolts) {
    return millivolts > 3000 && millivolts < 4200;
}

void monitor_cells(void) {
    if (!check_cell_voltage(read_cell_sample())) {
        fault_flags |= 1u;
    }
    update_state();
}

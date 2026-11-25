#ifndef CIE_BMS_H
#define CIE_BMS_H
extern volatile unsigned fault_flags;
void monitor_cells(void);
int check_cell_voltage(int millivolts);
void update_state(void);
void report_can(void);
#endif

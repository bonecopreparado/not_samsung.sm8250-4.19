/* SPDX-License-Identifier: GPL-2.0 */
/* Host fixture: the driver function and register definitions are extracted. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
#define CONFIG_BATTERY_SAMSUNG 1
#define BIT(n) (1U << (n))
#define BITS(hi, lo) (((1U << ((hi) - (lo) + 1)) - 1) << (lo))
#include "pca9468_registers_under_test.h"

enum { POWER_SUPPLY_STATUS_CHARGING, POWER_SUPPLY_STATUS_NOT_CHARGING };
enum { POWER_SUPPLY_HEALTH_GOOD, POWER_SUPPLY_HEALTH_DC_ERR };
enum { DC_STATE_NO_CHARGING };
struct pca9468_charger { int chg_status, health_status, charging_state; };
static int sts_b_result, int1_result, voltage;
static unsigned int sts_b, int1_sts;
static int info_logs, error_logs, debug_logs, register_dumps;
static int read_sts_b, read_int1;
#define pr_info(...) ((void)info_logs++)
#define pr_err(...) ((void)error_logs++)
#define pr_debug(...) ((void)debug_logs++)

static int pca9468_read_reg(struct pca9468_charger *charger, unsigned int reg,
                            unsigned int *value)
{
    (void)charger;
    if (reg == PCA9468_REG_STS_B) {
        read_sts_b++;
        if (sts_b_result < 0) return sts_b_result;
        *value = sts_b;
        return 0;
    }
    if (reg == PCA9468_REG_INT1_STS) {
        read_int1++;
        /* regmap_read leaves the preceding value intact when the bus fails. */
        if (int1_result < 0) return int1_result;
        *value = int1_sts;
        return 0;
    }
    return -EINVAL;
}
static int pca9468_bulk_read_reg(struct pca9468_charger *charger, unsigned int reg,
                                u8 *value, unsigned int count)
{
    (void)charger;
    (void)reg;
    memset(value, 0, count);
    return 0;
}
static int pca9468_read_adc(struct pca9468_charger *charger, unsigned int channel)
{
    (void)charger;
    return channel == ADCCH_VBAT ? voltage : 0;
}
static void pca9468_test_read(struct pca9468_charger *charger)
{
    (void)charger;
    register_dumps++;
}
static void msleep(unsigned int milliseconds) { (void)milliseconds; }

#include "pca9468_function_under_test.h"

static int checks, failures;
#define CHECK(condition) do { checks++; if (!(condition)) { \
    failures++; printf("FAIL line %d: %s\n", __LINE__, #condition); } } while (0)

static struct pca9468_charger reset(void)
{
    struct pca9468_charger charger = { 0, 0, 1 };
    sts_b_result = int1_result = 0;
    sts_b = PCA9468_BIT_ACTIVE_STATE_STS;
    int1_sts = 0;
    voltage = PCA9468_DC_VBAT_MIN + 100000;
    info_logs = error_logs = debug_logs = register_dumps = 0;
    read_sts_b = read_int1 = 0;
    return charger;
}

int main(void)
{
    struct pca9468_charger charger = reset();
    CHECK(pca9468_check_error(&charger) == 0);
    CHECK(read_sts_b == 1 && read_int1 == 1);
    CHECK(info_logs == 0 && debug_logs == 1 && error_logs == 0);
    CHECK(charger.health_status == POWER_SUPPLY_HEALTH_GOOD);
    CHECK(register_dumps == 1);

    charger = reset();
    sts_b_result = -EIO;
    CHECK(pca9468_check_error(&charger) == -EIO);
    CHECK(read_sts_b == 1 && read_int1 == 0);
    CHECK(info_logs == 1 && debug_logs == 0);
    CHECK(register_dumps == 0);

    charger = reset();
    int1_result = -EIO;
    CHECK(pca9468_check_error(&charger) == -EIO);
    CHECK(read_sts_b == 1 && read_int1 == 1);
    CHECK(info_logs == 1 && debug_logs == 0);
    CHECK(register_dumps == 0);

    charger = reset();
    int1_sts = PCA9468_BIT_TEMP_REG_STS;
    CHECK(pca9468_check_error(&charger) == -EINVAL);
    CHECK(error_logs == 1 && info_logs == 1 && debug_logs == 0);
    CHECK(charger.health_status == POWER_SUPPLY_HEALTH_DC_ERR);
    CHECK(charger.chg_status == POWER_SUPPLY_STATUS_NOT_CHARGING);

    charger = reset();
    voltage = PCA9468_DC_VBAT_MIN;
    CHECK(pca9468_check_error(&charger) == -EINVAL);
    CHECK(read_int1 == 0);
    CHECK(error_logs == 1 && info_logs == 1 && debug_logs == 0);
    CHECK(charger.health_status == POWER_SUPPLY_HEALTH_DC_ERR);

    charger = reset();
    for (int i = 0; i < 1000; i++) {
        if (pca9468_check_error(&charger) != 0) failures++;
    }
    CHECK(info_logs == 0 && error_logs == 0 && debug_logs == 1000);
    CHECK(read_sts_b == 1000 && read_int1 == 1000);
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}

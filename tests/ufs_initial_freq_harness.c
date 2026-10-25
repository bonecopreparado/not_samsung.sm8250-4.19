/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual UFS initialization and simple_ondemand code, mocked framework only. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

typedef unsigned int u32;
struct device { int unused; };
struct devfreq_dev_status {
    unsigned long total_time, busy_time, current_frequency;
};
struct devfreq_simple_ondemand_data {
    unsigned int upthreshold, downdifferential;
    int simple_scaling;
};
struct devfreq {
    unsigned long max_freq, min_freq, previous_freq;
    void *data;
    struct devfreq_dev_status last_status;
};
struct devfreq_dev_profile {
    unsigned long initial_freq;
    unsigned int polling_ms;
    int (*target)(struct device *, unsigned long *, u32);
    int (*get_dev_status)(struct device *, struct devfreq_dev_status *);
};
struct ufs_clk_info { unsigned long min_freq, max_freq, curr_freq; };
struct list_head { struct ufs_clk_info *first; };
struct ufs_clk_scaling { struct devfreq_dev_profile profile; };
struct ufs_hba {
    struct device *dev;
    struct list_head clk_list_head;
    struct ufs_clk_scaling clk_scaling;
    struct devfreq *devfreq;
};
#define list_empty(head) (!(head)->first)
#define list_first_entry(head, type, member) ((head)->first)
#define IS_ERR(p) ((intptr_t)(p) < 0 && (intptr_t)(p) >= -4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define DEVFREQ_GOV_SIMPLE_ONDEMAND "simple_ondemand"
#define dev_err(...) ((void)0)
#define DFSO_UPTHRESHOLD 90
#define DFSO_DOWNDIFFERENCTIAL 5

static unsigned int checks, failures, adds, removes, registrations;
static unsigned long removed[2];
static int registration_error;
static struct devfreq df;
static struct devfreq_simple_ondemand_data ufs_governor = {70, 65, 1};
static void *gov_data = &ufs_governor;
static const char *scenario;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    fprintf(stderr, "FAIL %s: %s (line%d)\n", scenario, #c, __LINE__); } } while (0)

static int ufshcd_devfreq_target(struct device *dev, unsigned long *freq, u32 flags)
{ (void)dev; (void)freq; (void)flags; return 0; }
static int ufshcd_devfreq_get_dev_status(struct device *dev, struct devfreq_dev_status *status)
{ (void)dev; (void)status; return 0; }
static int dev_pm_opp_add(struct device *dev, unsigned long freq, unsigned long voltage)
{ (void)dev; (void)freq; (void)voltage; adds++; return 0; }
static void dev_pm_opp_remove(struct device *dev, unsigned long freq)
{ (void)dev; if (removes < 2) removed[removes] = freq; removes++; }
static struct devfreq *devfreq_add_device(struct device *dev,
        struct devfreq_dev_profile *profile, const char *governor, void *data)
{
    (void)dev;
    CHECK(strcmp(governor, DEVFREQ_GOV_SIMPLE_ONDEMAND) == 0);
    registrations++;
    if (registration_error)
        return (void *)(intptr_t)registration_error;
    /* This is the exact framework invariant in devfreq_add_device(). */
    df.previous_freq = profile->initial_freq;
    df.last_status.current_frequency = profile->initial_freq;
    df.data = data;
    return &df;
}
static int devfreq_update_stats(struct devfreq *devfreq)
{ (void)devfreq; return 0; }
static unsigned long long div_u64(unsigned long long dividend, unsigned int divisor)
{ return dividend / divisor; }

#include "ufs_initial_freq_under_test.h"
#include "simpleondemand_under_test.h"

static void reset(const char *name)
{
    scenario = name;
    memset(&df, 0, sizeof(df));
    adds = removes = registrations = 0;
    registration_error = 0;
}

static void recorded_clock(unsigned long maximum, unsigned long current)
{
    struct device dev = {0};
    struct ufs_clk_info clock = {37500000, maximum, current};
    struct ufs_hba hba;
    unsigned long requested = ULONG_MAX;
    memset(&hba, 0, sizeof(hba));
    hba.dev = &dev;
    hba.clk_list_head.first = &clock;
    reset(maximum == 333333333 ? "333MHz recorded clock" : "300MHz recorded clock");
    CHECK(ufshcd_devfreq_init(&hba) == 0);
    CHECK(hba.devfreq == &df && adds == 2 && registrations == 1 && removes == 0);
    CHECK(hba.clk_scaling.profile.initial_freq == current);
    CHECK(df.previous_freq == current);
    CHECK(hba.clk_scaling.profile.polling_ms == 60);
    df.max_freq = maximum;
    df.min_freq = clock.min_freq;
    /* UFS's first status call starts the window with total=busy=0. */
    CHECK(devfreq_simple_ondemand_func(&df, &requested) == 0);
    CHECK(requested == current);
    df.last_status.total_time = 100;
    df.last_status.busy_time = 50;
    CHECK(devfreq_simple_ondemand_func(&df, &requested) == 0);
    CHECK(requested == current);
    df.last_status.busy_time = 1;
    CHECK(devfreq_simple_ondemand_func(&df, &requested) == 0);
    CHECK(requested == clock.min_freq);
    df.last_status.busy_time = 90;
    CHECK(devfreq_simple_ondemand_func(&df, &requested) == 0);
    CHECK(requested == maximum);
}

int main(void)
{
    struct device dev = {0};
    struct ufs_clk_info clock = {37500000, 333333333, 333333333};
    struct ufs_hba hba;
    recorded_clock(300000000, 300000000);
    recorded_clock(333333333, 333333333);
    recorded_clock(333333333, 37500000);
    /* Unknown cache remains unspecified; do not invent a hardware rate. */
    recorded_clock(333333333, 0);

    reset("empty clock list does not register devfreq");
    memset(&hba, 0, sizeof(hba));
    hba.dev = &dev;
    CHECK(ufshcd_devfreq_init(&hba) == 0);
    CHECK(!hba.devfreq && !registrations && !adds && !removes);

    reset("registration failure releases both OPPs");
    hba.clk_list_head.first = &clock;
    registration_error = -ENOMEM;
    CHECK(ufshcd_devfreq_init(&hba) == -ENOMEM);
    CHECK(hba.devfreq == 0 && registrations == 1);
    CHECK(removes == 2 && removed[0] == clock.min_freq && removed[1] == clock.max_freq);
    printf("%u UFS initial-frequency/governor checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}

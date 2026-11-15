package config

// RequestLimits are per-replica admission capacities and shared Redis rate budgets.
// Tune on staging together with replicas * DB_MAX_OPEN_CONNS, not in isolation.
type RequestLimits struct {
	IPPerMinute     int64
	UserPerMinute   int64
	CostlyPerMinute int64
	Requests        int
	Uploads         int
	Streams         int
	Costly          int
	Callbacks       int
	StreamsPerUser  int
	EffectWorkers   int
}

func DefaultRequestLimits() RequestLimits {
	return RequestLimits{
		IPPerMinute:     6000,
		UserPerMinute:   300,
		CostlyPerMinute: 20,
		Requests:        128,
		Uploads:         4,
		Streams:         128,
		Costly:          8,
		Callbacks:       8,
		StreamsPerUser:  2,
		EffectWorkers:   2,
	}
}
func loadRequestLimits() RequestLimits {
	d := DefaultRequestLimits()
	return RequestLimits{
		IPPerMinute:     getEnvAsInt64("LMS_IP_RATE_PER_MINUTE", d.IPPerMinute),
		UserPerMinute:   getEnvAsInt64("LMS_USER_RATE_PER_MINUTE", d.UserPerMinute),
		CostlyPerMinute: getEnvAsInt64("LMS_COSTLY_RATE_PER_MINUTE", d.CostlyPerMinute),
		Requests:        getEnvAsInt("LMS_MAX_REQUESTS", d.Requests),
		Uploads:         getEnvAsInt("LMS_MAX_UPLOADS", d.Uploads),
		Streams:         getEnvAsInt("LMS_MAX_STREAMS", d.Streams),
		Costly:          getEnvAsInt("LMS_MAX_COSTLY_REQUESTS", d.Costly),
		Callbacks:       getEnvAsInt("LMS_MAX_CALLBACKS", d.Callbacks),
		StreamsPerUser:  getEnvAsInt("LMS_MAX_STREAMS_PER_USER", d.StreamsPerUser),
		EffectWorkers:   getEnvAsInt("LMS_QUIZ_EFFECT_WORKERS", d.EffectWorkers),
	}
}

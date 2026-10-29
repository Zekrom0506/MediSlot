| Run | API copies (1 CPU each) | Requests/s | p50 | p95 | p99 | Failed requests | Peak Postgres connections | Connections refused by Postgres | API CPU | Race test (100 at once) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-copy | 1 | 413.8 | 4200 ms | 4400 ms | 4500 ms | 203 of 54147 (0.37%) | 41 of 100 | 0 | 33% | correct: 1 booked, 99 told "just taken", spread over 1 copies |
| 3-copies | 3 | 1003.1 | 550 ms | 1000 ms | 1100 ms | 6282 of 131275 (4.79%) | 100 of 100 | 6865 | 55% | correct: 1 booked, 99 told "just taken", spread over 3 copies |
| 3-copies-pgbouncer | 3 | 1011.0 | 700 ms | 960 ms | 1000 ms | 0 of 132328 (0.00%) | 41 of 100 | 0 | 54% | correct: 1 booked, 99 told "just taken", spread over 3 copies |

Most common failures:

- 1-copy: 90x GET /api/doctors/[id]/slots: HTTPError('502 Server Error: Bad Gateway for url: GET /api/doctors/[id]/slots')
- 1-copy: 63x GET /api/doctors: HTTPError('502 Server Error: Bad Gateway for url: GET /api/doctors')
- 1-copy: 26x POST /api/bookings: CatchResponseError('unexpected status 502')
- 3-copies: 2754x GET /api/doctors/[id]/slots: HTTPError('500 Server Error: Internal Server Error for url: GET /api/doctors/[id]/slots')
- 3-copies: 2010x GET /api/doctors: HTTPError('500 Server Error: Internal Server Error for url: GET /api/doctors')
- 3-copies: 828x GET /api/bookings/me: HTTPError('500 Server Error: Internal Server Error for url: GET /api/bookings/me')

Setup: 2500 simulated patients per 180 second run, measured after all of them had started (Locust --reset-stats); logins are not part of it. "Connections refused" counts PostgreSQL "sorry, too many clients already" errors. A request that fails that way is a capacity problem, not a double booking. Host: Apple M4, Docker with 10 CPUs. "API CPU" is the average per copy during the run; near 100% means the copies were the bottleneck, as intended.

"""Filho com RLIMIT_AS de 512 MiB tenta alocar 1 GiB: deve morrer com MemoryError (código de saída != 0) sem afetar o pai.
Também mede: RSS de um processo Python que importa app.db + psycopg2 (base do worker) e o de procrastinate."""
import multiprocessing as mp, resource, os, sys, time
def filho():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    x = bytearray(1024*1024*1024); x[0] = 1  # 1 GiB
    print("filho alocou 1 GiB: NÃO deveria"); sys.exit(0)
if __name__ == "__main__":
    mp.set_start_method("fork")
    t0 = time.perf_counter(); p = mp.Process(target=filho); p.start(); p.join(30)
    print(f"filho_exitcode={p.exitcode} tempo_s={time.perf_counter()-t0:.2f} (esperado: !=0 por MemoryError)")
    def rss(): return int(open('/proc/self/status').read().split('VmRSS:')[1].split()[0])
    print(f"rss_kb_pai_python_puro={rss()}")
    import psycopg2, app.db, app.log, app.settings  # noqa
    print(f"rss_kb_com_app_db_psycopg2={rss()}")
    import procrastinate  # noqa
    print(f"rss_kb_mais_procrastinate={rss()}")

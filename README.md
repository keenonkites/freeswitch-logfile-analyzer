```
usage: analyze [-h] [-d DATABASE] [-e ENCODING] [-o {all,events,summary}] logfile

Freeswitch logfile analyzer

positional arguments:
  logfile               Path to Freeswitch logfile to analyze

options:
  -h, --help            show this help message and exit
  -d DATABASE, --database DATABASE
                        If set, results will be stored into an SQLite3 database
                        under the given filename
  -e ENCODING, --encoding ENCODING
                        Encoding of the log file
  -o {all,events,summary}, --output {all,events,summary}
                        Print selected results to STDOUT

Examples:
  analyze freeswitch.log
  analyze --output summary freeswitch.log
  analyze --encoding latin-1 freeswitch.log
  analyze --database log-$(date +'%Y-%m-%d-%H:%M:%S').db --encoding latin-1 freeswitch.log
```

# XLOGIX Call Trace Explorer

## Overview

XLOGIX Call Trace Explorer is a FastAPI-based application for searching,
correlating and reconstructing customer calls from FreeSWITCH ESL event logs.

FreeSWITCH produces many events for a single call. A call can contain multiple
channel legs, transfers, queue activity, agent attempts, recordings, DTMF
events and hangups.

The application parses these events, normalizes important fields, correlates
related UUIDs and reconstructs them into a single call history.

The project is designed around UUID relationships rather than log-line
position because multiple calls and multiple FreeSWITCH hosts can be
interleaved in the same log file.

---

# Architecture

```text
FreeSWITCH ESL Logs
        |
        v
   LogReader
        |
        v
   EventParser
        |
        v
 EventNormalizer
        |
        v
   ParsedEvent
        |
        v
  CallCorrelator
        |
        v
    CallFinder
        |
        v
    CallTracer
        |
        v
      FastAPI
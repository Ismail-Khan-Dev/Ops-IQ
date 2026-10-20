"""OpenTelemetry distributed tracing for OpsIQ.

Exports traces via OTLP to Grafana Tempo and metrics via Prometheus.
"""

import logging
import os

logger = logging.getLogger("ecommerce_ops.otel")

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "opsiq-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")
OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
OTEL_TRACES_SAMPLER = os.getenv("OTEL_TRACES_SAMPLER", "parentbased_traceidratio")
OTEL_TRACES_SAMPLER_ARG = os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1")


def init_tracing():
    """Initialize OpenTelemetry SDK with OTLP exporter."""
    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing disabled (OTEL_ENABLED=false)")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.baggage.propagation import W3CBaggagePropagator
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        # Set W3C Trace Context + Baggage propagators
        set_global_textmap(
            CompositePropagator(
                [
                    TraceContextTextMapPropagator(),
                    W3CBaggagePropagator(),
                ]
            )
        )

        # Resource
        resource = Resource.create(
            {
                SERVICE_NAME: OTEL_SERVICE_NAME,
                "deployment.environment": os.getenv("ENV", "development"),
                "service.version": "0.2.0",
            }
        )

        # Tracer Provider
        tracer_provider = TracerProvider(
            resource=resource,
            sampler=_get_sampler(),
        )
        otlp_exporter = OTLPSpanExporter(
            endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Meter Provider with Prometheus exporter
        prometheus_reader = PrometheusMetricReader()
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[prometheus_reader],
        )
        from opentelemetry import metrics

        metrics.set_meter_provider(meter_provider)

        # Auto-instrument httpx (outgoing HTTP calls)
        HTTPXClientInstrumentor().instrument()

        logger.info(
            "OpenTelemetry tracing initialized: service=%s, endpoint=%s, sampler=%s=%s",
            OTEL_SERVICE_NAME,
            OTEL_EXPORTER_OTLP_ENDPOINT,
            OTEL_TRACES_SAMPLER,
            OTEL_TRACES_SAMPLER_ARG,
        )

        return tracer_provider

    except ImportError as e:
        logger.warning("OpenTelemetry packages not installed: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to initialize OpenTelemetry: %s", e)
        return None


def _get_sampler():
    from opentelemetry.sdk.trace.sampling import (
        ALWAYS_ON,
        ParentBasedTraceIdRatio,
        TraceIdRatioBased,
    )

    ratio = float(OTEL_TRACES_SAMPLER_ARG)

    if OTEL_TRACES_SAMPLER == "traceidratio":
        return TraceIdRatioBased(ratio)
    elif OTEL_TRACES_SAMPLER == "parentbased_traceidratio":
        return ParentBasedTraceIdRatio(ratio)
    elif OTEL_TRACES_SAMPLER == "always_on":
        return ALWAYS_ON
    else:
        return ParentBasedTraceIdRatio(0.1)


def get_tracer(name: str = "ecommerce_ops"):
    """Get a tracer instance for manual instrumentation."""
    from opentelemetry import trace

    return trace.get_tracer(name)


def instrument_app(app):
    """Instrument a FastAPI app with OpenTelemetry."""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,ready,live,metrics",
            server_request_hook=_server_request_hook,
            client_request_hook=_client_request_hook,
        )
        logger.info("FastAPI app instrumented with OpenTelemetry")
    except Exception as e:
        logger.warning("Failed to instrument FastAPI: %s", e)


def _server_request_hook(span, scope):
    """Add custom attributes to server spans."""
    if span and span.is_recording():
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode()
        if request_id:
            span.set_attribute("http.request_id", request_id)


def _client_request_hook(span, request):
    """Add custom attributes to client request spans."""
    if span and span.is_recording():
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))

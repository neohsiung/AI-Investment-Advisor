export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const { NodeSDK } = await import('@opentelemetry/sdk-node');
    const { OTLPTraceExporter } = await import('@opentelemetry/exporter-trace-otlp-http');
    const { resourceFromAttributes } = await import('@opentelemetry/resources');
    const { SEMRESATTRS_SERVICE_NAME } = await import('@opentelemetry/semantic-conventions');

    const sdk = new NodeSDK({
      resource: resourceFromAttributes({
        [SEMRESATTRS_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'nextjs_frontend',
      }),
      traceExporter: new OTLPTraceExporter({
        url: (process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://otel-collector:4318').endsWith('/v1/traces') 
          ? process.env.OTEL_EXPORTER_OTLP_ENDPOINT 
          : `${process.env.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces`,
      }),
    });

    sdk.start();
    console.log('✓ OpenTelemetry Initialized for Next.js');
  }
}

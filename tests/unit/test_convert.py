from paper_pdf_ingest.convert import choose_tool, detect_gpu_vram_gb


class TestDetectGpuVram:
    def test_returns_float(self):
        result = detect_gpu_vram_gb()
        assert isinstance(result, float)

    def test_returns_non_negative(self):
        result = detect_gpu_vram_gb()
        assert result >= 0.0


class TestChooseTool:
    def test_returns_valid_tool(self):
        tool = choose_tool()
        assert tool in ('marker', 'pymupdf4llm')

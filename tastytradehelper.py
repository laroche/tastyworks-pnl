class TastytradeHelper:
	CASH_SETTLED_SYMBOLS = ["SPXW", "SPX", "VIXW"]

	"""
	Helper class for Tastytrade data processing.
	"""
	@staticmethod
	def is_symbol_cash_settled(symbol: str) -> bool:
		"""
		Check if the given symbol is cash settled.
		
		Args:
			symbol (str): The symbol to check.
		
		Returns:
			bool: True if the symbol is cash settled, False otherwise.
		"""
		core_symbol = symbol.split()[0]
		return any(core_symbol.startswith(prefix) for prefix in TastytradeHelper.CASH_SETTLED_SYMBOLS)
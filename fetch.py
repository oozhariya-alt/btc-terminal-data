  import requests
  import json
  from datetime import datetime, timezone

  YAHOO_SYMBOLS = {
      'spx':    '^GSPC',
      'nasdaq': '^IXIC',
      'vix':    '^VIX',
      'us10y':  '^TNX',
      'gold':   'GC=F',
  }

  DIVIDE_BY_10 = {'us10y'}

  UA = 'Mozilla/5.0 (compatible; btc-terminal/1.0)'


  def fetch_yahoo(symbol):
      url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol
      params = {'range': '1mo', 'interval': '1d'}
      try:
          r = requests.get(url, params=params, headers={'User-Agent': UA}, timeout=15)
          r.raise_for_status()
          d = r.json()
          result = d['chart']['result'][0]
          meta = result['meta']
          quote = result['indicators']['quote'][0]
          closes = [c for c in quote['close'] if c is not None]
          if len(closes) < 2:
              return None
          current = meta.get('regularMarketPrice') or closes[-1]
          first = closes[0]
          return {
              'value': round(current, 2),
              'change_30d_pct': round((current / first - 1) * 100, 2),
          }
      except Exception as e:
          print('  fail', symbol, '-', e)
          return None


  def main():
      now = datetime.now(timezone.utc)
      print('Fetching at', now.isoformat())
      tradfi = {}
      for key, symbol in YAHOO_SYMBOLS.items():
          print('  ->', key, '(', symbol, ')')
          data = fetch_yahoo(symbol)
          if data:
              if key in DIVIDE_BY_10:
                  data['value'] = round(data['value'] / 10, 2)
              tradfi[key] = data
              print('     ok', data['value'], '(', data['change_30d_pct'], '% 30d)')
      output = {
          'tradfi': tradfi,
          'updated_at': now.isoformat(),
      }
      with open('data.json', 'w') as f:
          json.dump(output, f, indent=2)
      print('Saved', len(tradfi), 'indicators to data.json')


  if __name__ == '__main__':
      main()

# -*- coding: utf-8 -*-

import math
import time
from config.settings import settings


class BAR(object):
    def __init__(self, tick_second, tick_price, units):
        # BAR 생성 시각
        adjust_seconds = math.trunc(tick_second / units) * units
        self.start_time = self.end_time = adjust_seconds

        self.dirty = False

        self.openPrice = self.highPrice = self.lowPrice = self.closePrice = tick_price

        self.priceLong = tick_price
        self.priceShort = tick_price

        self.vpinLong = 0.0
        self.vpinShort = 0.0

        self.totalCnt = 0
        self.totalVolume = 0
        self.totalAmt = 0.0
        self.askCnt = 0
        self.bidCnt = 0
        self.askVolume = 0
        self.bidVolume = 0
        self.askAmt = 0.0
        self.bidAmt = 0.0

        self.bounceCnt = 0
        self.bounceUpDown = 0
        self.bouncePrice = 0
        self.bounceShort = 0.0
        self.bounceLong = 0.0


class CHART(object):
    def __init__(self, symbol="", units=300):
        """ 차트 생성자 """

        self.symbol = symbol
        self.units = units
        self.longAlpha = 2.0 / (settings.LONG_WINDOW_SIZE + 1.0)
        self.shortAlpha = 2.0 / (settings.SHORT_WINDOW_SIZE + 1.0)

        self.candles = []

    def make_hist_bar(self, data):
        self.candles = []

        for bar in data:
            seconds = bar[0] / 1000
            open_price = bar[1]
            high_price = bar[2]
            low_price = bar[3]
            close_price = bar[4]
            volume = bar[5]
            if seconds is None or open_price is None or high_price is None or low_price is None or close_price is None \
                    or volume is None:
                continue

            self.create_bar(seconds, open_price)
            cur_candle = self.candles[-1]
            cur_candle.openPrice = open_price
            cur_candle.closePrice = close_price
            cur_candle.highPrice = high_price
            cur_candle.lowPrice = low_price
            cur_candle.totalVolume = volume

        self.print_bar()

    def create_bar(self, tick_seconds, tick_price):
        """ BAR 생성 """

        # 적정 수준의 캔들을 유지
        if len(self.candles) > 200:
            self.candles.pop(0)

        new_candle = BAR(tick_seconds, tick_price, self.units)
        if len(self.candles) > 0:
            prev_candle = self.candles[-1]
            new_candle.bouncePrice = prev_candle.bouncePrice
            new_candle.bounceUpDown = prev_candle.bounceUpDown
        else:
            new_candle.bouncePrice = tick_price
            new_candle.bounceUpDown = 0

        self.candles.append(new_candle)

    def update_bar(self, tick_seconds, tick_price, tick_dir, tick_volume):
        """ 틱 업데이트 """

        # 최종 바 가져오기
        cur_candle = self.candles[-1]

        # 최종 시간 갱신
        cur_candle.end_time = tick_seconds

        # 고가, 저가 갱신
        if cur_candle.highPrice < tick_price:
            cur_candle.highPrice = tick_price
        if cur_candle.lowPrice > tick_price:
            cur_candle.lowPrice = tick_price

        # 종가 갱신
        cur_candle.closePrice = tick_price

        # 거래량 갱신
        cur_candle.totalVolume += tick_volume
        cur_candle.totalAmt += tick_price * tick_volume
        cur_candle.totalCnt += 1
        if tick_dir == 1:
            cur_candle.askCnt += 1
            cur_candle.askVolume += tick_volume
            cur_candle.askAmt += tick_price * tick_volume
        else:
            cur_candle.bidCnt += 1
            cur_candle.bidVolume += tick_volume
            cur_candle.bidAmt += tick_price * tick_volume

        # bounce
        '''
        if cur_candle.bouncePrice == tick_price:
            if cur_candle.bounceUpDown == 1:
                cur_candle.bounceCnt = cur_candle.bounceCnt + 1
            elif cur_candle.bounceUpDown == -1:
                cur_candle.bounceCnt = cur_candle.bounceCnt - 1
        '''
        if cur_candle.bouncePrice < tick_price:
            cur_candle.bounceCnt = cur_candle.bounceCnt + 1
            cur_candle.bouncePrice = tick_price
            cur_candle.bounceUpDown = 1
        elif cur_candle.bouncePrice > tick_price:
            cur_candle.bounceCnt = cur_candle.bounceCnt - 1
            cur_candle.bouncePrice = tick_price
            cur_candle.bounceUpDown = -1

        # 이전 바 가져오기
        if len(self.candles) > 2:
            prev_candle = self.candles[-2]

            # 이동평균 가격
            cur_candle.priceLong = (1 - self.longAlpha) * prev_candle.priceLong + self.longAlpha * cur_candle.closePrice
            cur_candle.priceShort = (1 - self.shortAlpha) * prev_candle.priceShort + self.shortAlpha * cur_candle.closePrice

            # VPIN
            cur_candle.vpinLong = (1 - self.longAlpha) * prev_candle.vpinLong + self.longAlpha * ((cur_candle.askVolume - cur_candle.bidVolume) / self.units) * 100.0
            cur_candle.vpinShort = (1 - self.shortAlpha) * prev_candle.vpinShort + self.shortAlpha * ((cur_candle.askVolume - cur_candle.bidVolume) / self.units) * 100.0

            # Bounce
            cur_candle.bounceLong = (1 - self.longAlpha) * prev_candle.bounceLong + self.longAlpha * cur_candle.bounceCnt
            cur_candle.bounceShort = (1 - self.shortAlpha) * prev_candle.bounceShort + self.shortAlpha * cur_candle.bounceCnt

        else:
            # 이동평균 가격
            cur_candle.priceLong = cur_candle.closePrice
            cur_candle.priceShort = cur_candle.closePrice

            # VPIN
            cur_candle.vpinLong = ((cur_candle.askVolume - cur_candle.bidVolume) / self.units) * 100.0
            cur_candle.vpinShort = ((cur_candle.askVolume - cur_candle.bidVolume) / self.units) * 100.0

            # Bounce
            cur_candle.bounceLong = cur_candle.bounceCnt
            cur_candle.bounceShort = cur_candle.bounceCnt

    def print_bar(self):
        if len(self.candles) > 0:
            candle = self.candles[-1]

            print('%s: %s, %.2f, %.2f, %.2f, %.2f, bounce = %.2f, %.2f' %
                  (self.symbol, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(candle.start_time)), candle.closePrice,
                   candle.vpinShort, candle.vpinLong, ((candle.askVolume - candle.bidVolume) / self.units) * 100.0), candle.bounceShort, candle.bounceLong)

    def make_bar(self, tick_seconds, tick_price, tick_dir, tick_volume):
        is_new = 0

        # 바 가 없으면 생성
        if len(self.candles) <= 0:
            self.create_bar(tick_seconds, tick_price)
            is_new = 1

        # 최종 바 가져오기
        cur_candle = self.candles[-1]

        # 거래량 소진 시 까지 반복
        while tick_volume > 0:
            # 최종 바 가져오기
            cur_candle = self.candles[-1]

            # 거래량 계산
            if self.units > (cur_candle.totalVolume + tick_volume):
                cur_volume = tick_volume
            else:
                cur_volume = self.units - cur_candle.totalVolume

            # 신규 바 생성 조건
            if cur_candle.totalVolume >= self.units:
                # self.print_bar()

                # 신규 바 생성
                self.create_bar(tick_seconds, tick_price)
                is_new = 1

            # 틱 업데이트
            self.update_bar(tick_seconds, tick_price, tick_dir, cur_volume)

            # 거래량 차감
            tick_volume -= cur_volume

        # 틱 업데이트
        self.update_bar(tick_seconds, tick_price, tick_dir, tick_volume)

        return is_new

import RPi.GPIO as GPIO
import datetime
import time
import pandas as pd
import logging
import logging.handlers
import sys

logger = logging.getLogger('fridge')
handler = logging.StreamHandler()
fHandler = logging.FileHandler('fridge.log')
formatter = logging.Formatter("%(asctime)s    %(levelname)s    %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
fHandler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(fHandler)
logger.setLevel(logging.DEBUG)
logging.captureWarnings(True)

dataLog = logging.getLogger('fridge.data')
dataFormatter = logging.Formatter("%(asctime)s, %(message)s", "%Y-%m-%d %H:%M:%S")
dataFileName = 'fridge-' + str(datetime.datetime.now()) + '.data'
dataHandler = logging.handlers.RotatingFileHandler(dataFileName, mode='w', maxBytes=10000, backupCount=2)
dataHandler.setFormatter(dataFormatter)
dataLog.addHandler(dataHandler)
dataLog.setLevel(logging.INFO)

class Fridge:
	def __init__(self, heaterGpio, coolerGpio, ambientTempSensorRomCode):
	
		self.initGpio(heaterGpio, coolerGpio)
		
		self.heater = TemperatureElement(heaterGpio, name='heater')
		self.cooler = TemperatureElement(coolerGpio, name='cooler')
		self.ambientTempSensor = DS18B20(ambientTempSensorRomCode, name='TempSens')		
		
		self.resultPeriod = datetime.timedelta(minutes=10)
		self.maxResults = 1000
		self.lastResultTime = None
		self.resultTime = datetime.datetime.now()
						
		self.resultsFile = 'results.txt'
		fo = open(self.resultsFile, 'w')
		fo.close()
		
	def initGpio(self, heaterGpioPin, coolerGpioPin):
		GPIO.setmode(GPIO.BCM)
		GPIO.setup(heaterGpioPin, GPIO.OUT)
		GPIO.setup(coolerGpioPin, GPIO.OUT)
		
	def updateResultsLog(self, dataFile):		
		if datetime.datetime.now() >= self.resultTime:
			now = datetime.datetime.now()
			names = ['date', 'set', 'meas', 'heater', 'cooler']
			d = pd.read_csv(dataFile, names=names)
			d['date'] = pd.to_datetime(d['date'])
			d['error'] = d.meas - d.set
			d['absError'] = d['error'].abs()
			if self.lastResultTime == None:
				dt = d
			else:
				start = self.lastResultTime
				end = self.resultTime
				mask = (d['date'] > start) & (d['date'] <= end)
				dt = d.loc[mask]
			
			mean = dt.meas.mean()
			maxErr = dt.error.max()
			minErr = dt.error.min()
			meanErr = dt.error.mean()
			meanAbsErr = dt.absError.mean()
			
			set = d['set'].iloc[-1]
			
			names = ['date', 'set', 'mean', 'maxErr', 'minErr', 'meanErr', 'meanAbsErr']
			d_r = pd.read_csv(self.resultsFile, names=names)
			
			try:
				fi = open(self.resultsFile, 'r')
				resBefore = fi.read()
				resBefore = resBefore.split('\n')
				fi.close()
			except:
				whatever = 1000
			
			fo = open(self.resultsFile, 'w')
			
			fo.write('{:11s}'.format('Date'))
			fo.write('{:9s}'.format('Time'))
			fo.write('{:5s}'.format('set'))
			fo.write('{:5s}'.format('mean'))
			fo.write('{:5s}'.format('maxE'))
			fo.write('{:5s}'.format('minE'))
			fo.write('{:6s}'.format('meanE'))
			fo.write('{:9s}'.format('meanAbsE') + '\n')
			
			fo.write( self.resultTime.strftime('%Y-%m-%d %H:%M:%S') + ' ' + '{:4.1f}'.format(set) + ' ' + '{:4.1f}'.format(mean) + ' ' + '{:4.1f}'.format(maxErr) + ' ' + '{:4.1f}'.format(minErr) + ' ' + '{:5.1f}'.format(meanErr) + ' ' + '{:8.1f}'.format(meanAbsErr) + '\n' )
			
			if len(resBefore) >= 2:
				for i in xrange(1, len(resBefore)-1, 1):
					fo.write(resBefore[i] + '\n')
					if i > self.maxResults:
						break
			
			fo.close()
			
			
			
			self.lastResultTime = self.resultTime
			self.resultTime = now + self.resultPeriod

class TemperatureElement:
	def __init__(self, bcmGpioNum, name='Name'):
		self.name = name
		self.gpioPin = bcmGpioNum
		self.on = None
		self.lastOnTime = None	
		self.minOnTime = datetime.timedelta(minutes=1)
		self.minOffTime = datetime.timedelta(minutes=3)
		
		try:
			GPIO.output(self.gpioPin, False)
			self.lastOffTime = datetime.datetime.now()
		except:
			logger.error('Failed to switch off in temp el init')
			raise

	def isOn(self):
		if(GPIO.input(self.gpioPin)):
			return True
		else:
			return False
	
	def status(self):
		if(GPIO.input(self.gpioPin)):
			try:
				onFor = str(datetime.datetime.now()-self.lastOnTime).split('.')[0]
			except:
				onFor = 'No Last On Time'
			logger.debug(self.name + " been ON for " + onFor)
			return self.name + " ON for " + onFor
		else:
			try:
				offFor = str(datetime.datetime.now()-self.lastOffTime).split('.')[0]
			except:
				offFor = 'No Last Off Time'
			logger.debug(self.name +" been OFF for " + offFor)
			return self.name +" OFF for " + offFor

	def turnOff(self):		
		now = datetime.datetime.now()
		switchOff = False
		#if not been on/off yet then can switch off
		if self.on == None:
			switchOff = True
		#if not been on yet, and not currently off then can switch off
		elif self.lastOnTime == None and self.on != False:
			switchOff = True
		#if on, and have been on for at least minOnTime then can switch off
		elif self.on == True:
			if (now - self.lastOnTime) > self.minOnTime:
				switchOff = True
			else:
				logger.debug(self.name + ' Unable to switch off. Min On Time not met' )
		elif self.on == False:
			switchOff = False # Already off
		else:
			logger.debug(self.name + ' Unable to switch off. Valid condition not found.' )				
		#Switch on if have decided to
		if switchOff == True:
			try:
				GPIO.output(self.gpioPin, False)
				self.lastOffTime = now
				self.on = False
				logger.debug(self.name + ' Switched Off Return 1' )
				return 1				
			except:
				logger.debug(self.name + ' Exception Return -1' )
				raise
				return -1
				
		else:
			logger.debug(self.name + ' No Change Return 0.' )
			return 0		
		
	def turnOn(self):		
		now = datetime.datetime.now()
		switchOn = False
		#if not been on/off yet then can switch on
		if self.on == None:
			switchOn = True
		#if not been off yet, and not currently on then can switch on
		elif self.lastOffTime == None and self.on != True:
			switchOn = True
		#if off, and have been off for at least minOffTime then can switch on
		elif self.on == False:
			if (now - self.lastOffTime) > self.minOffTime:
				switchOn = True
			else:
				logger.debug(self.name + ' Unable to switch on. Min Off Time not met' )
		elif self.on == True:
			switchOn = False # Already off				
		else:
			logger.debug(self.name + ' Unable to switch on. Valid condition not found.' )
		#Switch on if have decided to
		if switchOn == True:
			try:
				GPIO.output(self.gpioPin, True)
				self.lastOnTime = now
				self.on = True
				logger.debug(self.name + ' Switched On Return 1' )
				return 1				
			except:
				logger.debug(self.name + ' Exception Return -1' )
				raise
				return -1
		else:
			logger.debug(self.name + ' No Change Return 0' )
			return 0
		
class DS18B20:
	def __init__(self, romCode, name='Name'):
		self.name = name
		self.romCode = romCode
				
	def getTemp(self):
		tempFile = open('/sys/bus/w1/devices/' + self.romCode + '/w1_slave')
		tempText = tempFile.read()
		tempFile.close()
		tempData = tempText.split("\n")[1].split(" ")[9]
		temp = float(tempData[2:]) / 1000
		logger.debug(self.name + ' ' + str(temp))
		return temp

heaterGpio = 6
coolerGpio = 5
tempSensRomCode='28-0316027c72ff'

fridge = Fridge(heaterGpio, coolerGpio, tempSensRomCode)	

fridge.heater.minOffTime=datetime.timedelta(seconds=1)
fridge.heater.minOnTime=datetime.timedelta(seconds=1)
fridge.cooler.minOffTime=datetime.timedelta(minutes=3)
fridge.cooler.minOnTime=datetime.timedelta(minutes=1)
fridge.ambientTempSensor.getTemp()

samplePeriod = datetime.timedelta(seconds=10)

setTemp = 21


heaterOnHyst = 0.2 #Amount below set temp that heater is asked to switch on at
heaterOffHyst = 0.1 #Amount below set temp that heater is asked to switch off at
coolerOnHyst = 1.5  #Amount above set temp that cooler is asked to switch on at
coolerOffHyst = 1 #Amount above set temp that cooler is asked to switch off at


i=0
while True:
	try:
		i=i+1
		loopStartTime = datetime.datetime.now()

		temp = fridge.ambientTempSensor.getTemp()
		logger.debug('i=' + str(i) + ' Error=' + str(temp-setTemp) + ' Temp=' + str(temp) + ' Set temp=' + str(setTemp))
		temp = fridge.ambientTempSensor.getTemp()
		
		fridge.heater.status()
		fridge.cooler.status()	
		
		#Heater decision
		#If heater not on and temp is below set - heaterOnHyst then try to switch on
		if not fridge.heater.isOn():
			if temp < (setTemp - heaterOnHyst):
				fridge.heater.turnOn()			
		#If heater is on and temp above setTemp - heaetr OffHyst then try to switch off
		if fridge.heater.isOn():
			if temp > (setTemp - heaterOffHyst):
				fridge.heater.turnOff()	
				
		#Cooler decision
		#If cooler not on and temp is above set + coolerOnHyst then try to switch cooler on
		if not fridge.cooler.isOn():
			if temp > (setTemp + coolerOnHyst):
				fridge.cooler.turnOn()			
		#If cooler is on and temp below setTemp + coolerOffHyst then try to switch off
		if fridge.cooler.isOn():
			if temp < (setTemp + coolerOffHyst):
				fridge.cooler.turnOff()
			
		dataLog.info('{}'.format(setTemp) + ', ' + '{}'.format(temp) + ', ' +  str(fridge.heater.isOn()) + ', ' +  '{}'.format(fridge.cooler.isOn()) )		
		

		fridge.updateResultsLog(dataFileName)
				
		while datetime.datetime.now() < (loopStartTime + samplePeriod):
			doNothing = 1
			
	except KeyboardInterrupt:	
		logger.info('Ctrl-c Exit.')
		fridge.heater.turnOff()
		fridge.cooler.turnOff()
		sys.exit()		

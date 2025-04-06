#!/usr/bin/env python3
"""
Server BLE complet funcțional pentru controlul motoarelor cu PWM.
Folosește BlueZ cu D-Bus pentru o implementare robustă.

Acest script:
1. Configurează un serviciu BLE conectabil
2. Creează o caracteristică WRITABLE pentru primirea comenzilor
3. Execută comenzi pentru controlul motoarelor cu PWM în mod sigur pentru punțile H
4. Permite controlul vitezei cu valori între 0-100%
"""

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service

try:
    from gi.repository import GLib
except ImportError:
    import glib as GLib

import array
import RPi.GPIO as GPIO
import time
import logging
import sys

# Configurare logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BLE Robot")

# Configurare GPIO pentru controlul motoarelor
MOTOR1_FORWARD = 12  # GPIO pentru motorul 1 înainte
MOTOR1_BACKWARD = 13  # GPIO pentru motorul 1 înapoi
MOTOR2_FORWARD = 18  # GPIO pentru motorul 2 înainte
MOTOR2_BACKWARD = 19  # GPIO pentru motorul 2 înapoi

# Inițializare GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR1_FORWARD, GPIO.OUT)
GPIO.setup(MOTOR1_BACKWARD, GPIO.OUT)
GPIO.setup(MOTOR2_FORWARD, GPIO.OUT)
GPIO.setup(MOTOR2_BACKWARD, GPIO.OUT)

# Crearea obiectelor PWM - frecvența de 100 Hz este potrivită pentru motoare
pwm_motor1_forward = GPIO.PWM(MOTOR1_FORWARD, 100)
pwm_motor1_backward = GPIO.PWM(MOTOR1_BACKWARD, 100)
pwm_motor2_forward = GPIO.PWM(MOTOR2_FORWARD, 100)
pwm_motor2_backward = GPIO.PWM(MOTOR2_BACKWARD, 100)

# Pornirea PWM cu duty cycle 0 (motoare oprite)
pwm_motor1_forward.start(0)
pwm_motor1_backward.start(0)
pwm_motor2_forward.start(0)
pwm_motor2_backward.start(0)

# Variabilă pentru stocarea valorii de viteză
motor_speed = 100  # Valoare implicită 100%

# Pauză de stabilizare pentru a permite setărilor să se aplice
time.sleep(0.5)

# Funcția de siguranță pentru controlul PWM
def safe_output_pwm(pwm_pin, state, speed=None):
    """
    Funcție de siguranță pentru controlul motoarelor cu PWM
    
    Parametri:
    - pwm_pin: Obiectul PWM pentru pin
    - state: True pentru pornit, False pentru oprit
    - speed: Viteza (0-100%) - se folosește doar când state este True
    """
    if state:
        # Activează pinul cu viteza specificată
        pwm_pin.ChangeDutyCycle(speed)
    else:
        # Dezactivează pinul
        pwm_pin.ChangeDutyCycle(0)

def forward(speed=None):
    """
    Mișcă robotul înainte cu viteza specificată
    Dacă nu se specifică viteza, se folosește viteza globală
    """
    global motor_speed
    
    # Folosește viteza furnizată sau cea globală
    use_speed = speed if speed is not None else motor_speed
    
    print(f"Mers înainte cu viteza {use_speed}%")
    
    # Oprește întâi direcțiile opuse
    safe_output_pwm(pwm_motor1_backward, False)
    safe_output_pwm(pwm_motor2_backward, False)
    
    # Apoi activează direcțiile dorite cu viteza specificată
    safe_output_pwm(pwm_motor1_forward, True, use_speed)
    safe_output_pwm(pwm_motor2_forward, True, use_speed)

def backward(speed=None):
    """Mișcă robotul înapoi cu viteza specificată"""
    global motor_speed
    
    use_speed = speed if speed is not None else motor_speed
    
    print(f"Mers înapoi cu viteza {use_speed}%")
    
    safe_output_pwm(pwm_motor1_forward, False)
    safe_output_pwm(pwm_motor2_forward, False)
    
    safe_output_pwm(pwm_motor1_backward, True, use_speed)
    safe_output_pwm(pwm_motor2_backward, True, use_speed)

def turn_left(speed=None):
    """Viraj la stânga cu viteza specificată - rotire diferențială"""
    global motor_speed
    
    use_speed = speed if speed is not None else motor_speed
    
    print(f"Viraj stânga cu viteza {use_speed}%")
    
    # Roata stângă merge înapoi
    safe_output_pwm(pwm_motor1_forward, False)
    safe_output_pwm(pwm_motor1_backward, True, use_speed)
    
    # Roata dreaptă merge înainte
    safe_output_pwm(pwm_motor2_forward, True, use_speed)
    safe_output_pwm(pwm_motor2_backward, False)

def turn_right(speed=None):
    """Viraj la dreapta cu viteza specificată - rotire diferențială"""
    global motor_speed
    
    use_speed = speed if speed is not None else motor_speed
    
    print(f"Viraj dreapta cu viteza {use_speed}%")
    
    # Roata stângă merge înainte
    safe_output_pwm(pwm_motor1_forward, True, use_speed)
    safe_output_pwm(pwm_motor1_backward, False)
    
    # Roata dreaptă merge înapoi
    safe_output_pwm(pwm_motor2_forward, False)
    safe_output_pwm(pwm_motor2_backward, True, use_speed)

def stop():
    """Oprește toate motoarele"""
    print("Stop")
    
    safe_output_pwm(pwm_motor1_forward, False)
    safe_output_pwm(pwm_motor1_backward, False)
    safe_output_pwm(pwm_motor2_forward, False)
    safe_output_pwm(pwm_motor2_backward, False)

def process_command(command):
    """
    Procesează comanda primită și execută acțiunea corespunzătoare
    
    Formatul comenzii:
    - "F", "B", "L", "R", "S" - comenzi simple
    - "F:75", "B:50", etc. - comenzi cu parametru de viteză (0-100%)
    - "V:60" - setează viteza implicită la 60%
    """
    global motor_speed
    
    try:
        # Verifică dacă comanda include parametru de viteză
        if ":" in command:
            cmd, param = command.split(":", 1)
            speed = int(param)
            
            # Limitează viteza la intervalul 0-100%
            speed = max(0, min(100, speed))
            
            # Setează viteza globală sau execută comanda cu viteza specificată
            if cmd == "V":
                motor_speed = speed
                print(f"Viteza implicită setată la {speed}%")
                return
            elif cmd in "FBLRS":
                command = cmd  # Folosește doar partea de comandă pentru switch-ul de mai jos
                # Viteza va fi transmisă la funcțiile de control
            else:
                print(f"Comandă necunoscută: {command}")
                return
        else:
            # Comanda nu include parametru de viteză, se va folosi viteza implicită
            speed = None
        
        # Verificare suplimentară de siguranță
        if not command or command not in "FBLRSV":
            print(f'Comandă nerecunoscută: {command} - Oprire motoare pentru siguranță')
            stop()
            return
        
        # Execută comanda
        if command.startswith('F'):
            forward(speed)
        elif command.startswith('B'):
            backward(speed)
        elif command.startswith('L'):
            turn_left(speed)
        elif command.startswith('R'):
            turn_right(speed)
        elif command.startswith('S'):
            stop()
        else:
            print(f"Comandă necunoscută: {command}")
            stop()  # Oprire de siguranță
            
    except Exception as e:
        print(f"Eroare la procesarea comenzii: {e}")
        stop()  # Oprire de siguranță în caz de eroare

# Constante pentru definirea serviciului BLE
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# UUID-uri pentru serviciul și caracteristica BLE
# Folosim UUID-uri standard pentru compatibilitate maximă
SERVICE_UUID = '0000ffe0-0000-1000-8000-00805f9b34fb'
CHARACTERISTIC_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'

class Application(dbus.service.Object):
    """Clasa de bază pentru aplicația GATT."""
    
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_service(self, service):
        self.services.append(service)
    
    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        
        return response

class Service(dbus.service.Object):
    """Clasa pentru serviciul GATT."""
    
    PATH_BASE = '/org/bluez/example/service'
    
    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)
    
    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result
    
    def get_characteristics(self):
        return self.characteristics
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    """Clasa de bază pentru caracteristicile GATT."""
    
    PATH_BASE = '/org/bluez/example/characteristic'
    
    def __init__(self, bus, index, uuid, flags, service):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)
    
    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result
    
    def get_descriptors(self):
        return self.descriptors
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[GATT_CHRC_IFACE]
    
    @dbus.service.method(GATT_CHRC_IFACE,
                         in_signature='a{sv}',
                         out_signature='ay')
    def ReadValue(self, options):
        print('Caracteristică: ReadValue')
        return [0xff]
    
    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Caracteristică: WriteValue: %s' % value)
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        print('Caracteristică: StartNotify')
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        print('Caracteristică: StopNotify')

class RobotService(Service):
    """Serviciul GATT pentru controlul robotului."""
    
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, SERVICE_UUID, True)
        self.add_characteristic(CommandCharacteristic(bus, 0, self))

class CommandCharacteristic(Characteristic):
    """Caracteristica care primește comenzi pentru robot."""
    
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            CHARACTERISTIC_UUID,
            ['read', 'write'],
            service)
        self.value = [0x00]
    
    def ReadValue(self, options):
        print('Cerere citire valoare: %s' % options)
        return self.value
    
    def WriteValue(self, value, options):
        print('Cerere scriere valoare: %s %s' % (value, options))
        
        # Conversia de la bytes la string
        try:
            command = bytes(value).decode('utf-8')
            print('Comandă primită: %s' % command)
            
            # Procesează comanda inclusiv parametrul de viteză dacă există
            process_command(command)
            
        except Exception as e:
            print('Eroare la procesarea comenzii: %s' % e)
            # Oprire motoare în caz de eroare pentru siguranță
            stop()
        
        # Salvăm valoarea
        self.value = value

class Advertisement(dbus.service.Object):
    """Clasa pentru advertising-ul BLE."""
    
    PATH_BASE = '/org/bluez/example/advertisement'
    
    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = None
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(
                self.service_uuids, signature='s')
        
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(
                self.solicit_uuids, signature='s')
        
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(
                self.service_data, signature='sv')
        
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        
        if self.include_tx_power is not None:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        
        return {LE_ADVERTISEMENT_IFACE: properties}
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)
    
    def add_local_name(self, name):
        self.local_name = name
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]
    
    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('%s: Released!' % self.path)

class RobotAdvertisement(Advertisement):
    """Advertisement specific pentru robotul nostru."""
    
    def __init__(self, bus, index):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.add_service_uuid(SERVICE_UUID)
        self.add_local_name('RobotController')
        self.include_tx_power = True

def register_ad_cb():
    print('Advertisement înregistrat')

def register_ad_error_cb(error):
    print('Nu s-a putut înregistra advertisement-ul: ' + str(error))
    mainloop.quit()

def register_app_cb():
    print('Aplicația GATT înregistrată')

def register_app_error_cb(error):
    print('Nu s-a putut înregistra aplicația GATT: ' + str(error))
    mainloop.quit()

def find_adapter(bus):
    """Găsește adaptorul BlueZ."""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                              DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    
    for o, props in objects.items():
        if (LE_ADVERTISING_MANAGER_IFACE in props and
                GATT_MANAGER_IFACE in props):
            return o
    
    return None

# Funcție pentru curățare corectă la oprire
def cleanup():
    """Curăță resursele și oprește motoarele în siguranță"""
    print("Curățare resurse...")
    try:
        # Oprește toate motoarele pentru siguranță
        stop()
        
        # Oprește PWM
        pwm_motor1_forward.stop()
        pwm_motor1_backward.stop()
        pwm_motor2_forward.stop()
        pwm_motor2_backward.stop()
        
        # Eliberează resursele GPIO
        GPIO.cleanup()
    except Exception as e:
        print(f"Eroare la curățare: {e}")

def main():
    """Funcția principală."""
    global mainloop
    
    try:
        # Verificare inițială de siguranță
        print("Verificare stare inițială motoare...")
        stop()
        time.sleep(0.5)  # Pauză pentru stabilizare
        
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        
        bus = dbus.SystemBus()
        
        adapter = find_adapter(bus)
        if not adapter:
            print('BlueZ 5.0+ (GATT) nu este disponibil')
            return
        
        adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                      DBUS_PROP_IFACE)
        
        # Setează proprietățile adaptorului pentru vizibilitate
        adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
        adapter_props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(1))
        adapter_props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(1))
        adapter_props.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
        
        service_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE)
        
        ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                  LE_ADVERTISING_MANAGER_IFACE)
        
        # Creează aplicația GATT
        app = Application(bus)
        robot_service = RobotService(bus, 0)
        app.add_service(robot_service)
        
        # Înregistrează aplicația GATT
        service_manager.RegisterApplication(app.get_path(), {},
                                          reply_handler=register_app_cb,
                                          error_handler=register_app_error_cb)
        
        # Creează advertisement-ul
        robot_advertisement = RobotAdvertisement(bus, 0)
        
        # Înregistrează advertisement-ul
        ad_manager.RegisterAdvertisement(robot_advertisement.get_path(), {},
                                      reply_handler=register_ad_cb,
                                      error_handler=register_ad_error_cb)
        
        # Afișează instrucțiuni
        print('=====')
        print('Server BLE pentru robot pornit cu suport pentru controlul vitezei')
        print('Conectează-te la "RobotController" din aplicație')
        print('Comenzi:')
        print('  F - înainte cu viteza implicită')
        print('  B - înapoi cu viteza implicită')
        print('  L - stânga cu viteza implicită')
        print('  R - dreapta cu viteza implicită')
        print('  S - stop')
        print('  F:75 - înainte cu 75% viteză')
        print('  V:50 - setează viteza implicită la 50%')
        print('Apasă Ctrl+C pentru a opri')
        print('=====')
        
        mainloop = GLib.MainLoop()
        mainloop.run()
        
    except KeyboardInterrupt:
        print("\nServiciul BLE oprit de utilizator")
    except Exception as e:
        print(f"Eroare: {e}")
    finally:
        # Asigură-te că toate resursele sunt eliberate corect
        try:
            # Dezînregistrează advertisement-ul dacă există
            if 'ad_manager' in locals() and 'robot_advertisement' in locals():
                ad_manager.UnregisterAdvertisement(robot_advertisement.get_path())
            # Curăță resursele
            cleanup()
        except Exception as e:
            print(f"Eroare la eliberarea resurselor: {e}")

if __name__ == '__main__':
    # Înregistrează funcția de curățare și pentru semnale
    import atexit
    atexit.register(cleanup)
    
    # Inițiază aplicația
    main()
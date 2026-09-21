import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../flet_service.dart';

class UsbSerialService extends FletService {
  static const MethodChannel _channel = MethodChannel('flet/usb_serial');
  static const EventChannel _eventChannel = EventChannel('flet/usb_serial_events');
  StreamSubscription<dynamic>? _eventSub;

  UsbSerialService({required super.control});

  @override
  void init() {
    super.init();
    debugPrint("UsbSerialService(${control.id}).init");
    control.addInvokeMethodListener(_invokeMethod);
    _listenToEvents();
  }

  void _listenToEvents() {
    try {
      _eventSub = _eventChannel.receiveBroadcastStream().listen((dynamic event) {
        if (event is Map) {
          final type = event['type'] as String?;
          if (type == 'data') {
            control.triggerEvent("data", {"data": event['data']});
          } else if (type == 'attached') {
            control.triggerEvent("device_attached", {
              "device_name": event['device_name'],
              "vendor_id": event['vendor_id'],
              "product_id": event['product_id'],
            });
          } else if (type == 'detached') {
            control.triggerEvent("device_detached", {
              "device_name": event['device_name'],
              "vendor_id": event['vendor_id'],
              "product_id": event['product_id'],
            });
          }
        }
      }, onError: (dynamic error) {
        debugPrint("UsbSerialService: event error: $error");
      });
    } catch (e) {
      debugPrint("UsbSerialService: event channel unavailable: $e");
    }
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "list_ports":
        try {
          final List<dynamic>? ports = await _channel.invokeMethod('listPorts');
          return ports ?? [];
        } catch (e) {
          debugPrint("UsbSerialService.list_ports error: $e");
          return [];
        }

      case "open_port":
        try {
          final bool? success = await _channel.invokeMethod('openPort', args);
          return success ?? true;
        } catch (e) {
          debugPrint("UsbSerialService.open_port error: $e");
          return false;
        }

      case "close_port":
        try {
          final bool? success = await _channel.invokeMethod('closePort');
          return success ?? true;
        } catch (e) {
          debugPrint("UsbSerialService.close_port error: $e");
          return false;
        }

      case "write_data":
        try {
          final int? bytesWritten = await _channel.invokeMethod('writeData', args);
          return bytesWritten ?? 0;
        } catch (e) {
          debugPrint("UsbSerialService.write_data error: $e");
          return 0;
        }

      case "set_dtr":
        try {
          await _channel.invokeMethod('setDtr', args);
          return null;
        } catch (e) {
          debugPrint("UsbSerialService.set_dtr error: $e");
          return null;
        }

      case "set_rts":
        try {
          await _channel.invokeMethod('setRts', args);
          return null;
        } catch (e) {
          debugPrint("UsbSerialService.set_rts error: $e");
          return null;
        }

      default:
        throw Exception("Unknown UsbSerial method: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("UsbSerialService(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invokeMethod);
    _eventSub?.cancel();
    _eventSub = null;
    super.dispose();
  }
}

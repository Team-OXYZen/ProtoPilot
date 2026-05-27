
import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { delay } from 'rxjs/operators';
import { Room } from './room.model';

@Injectable({
  providedIn: 'root'
})
export class RoomService {

  private mockRooms: Room[] = [
    {
      id: '1',
      name: 'Deluxe Ocean View',
      description: 'A beautiful room with a stunning view of the ocean. Perfect for a romantic getaway.',
      price: 250,
      amenities: ['King Bed', 'Ocean View', 'Private Balcony', 'Jacuzzi'],
      imageUrl: 'assets/images/room1.jpg'
    },
    {
      id: '2',
      name: 'Cityscape Suite',
      description: 'A modern suite offering panoramic views of the city skyline. Ideal for business travelers.',
      price: 300,
      amenities: ['Queen Bed', 'City View', 'Work Desk', 'Mini Bar'],
      imageUrl: 'assets/images/room2.jpg'
    },
    {
      id: '3',
      name: 'Garden Retreat',
      description: 'A peaceful room overlooking our lush gardens. A perfect escape from the hustle and bustle.',
      price: 180,
      amenities: ['Twin Beds', 'Garden View', 'Patio', 'Rain Shower'],
      imageUrl: 'assets/images/room3.jpg'
    },
    {
      id: '4',
      name: 'Presidential Suite',
      description: 'The pinnacle of luxury. This suite offers unparalleled comfort and service.',
      price: 800,
      amenities: ['King Bed', 'Panoramic View', 'Private Pool', 'Butler Service'],
      imageUrl: 'assets/images/room4.jpg'
    }
  ];

  constructor() { }

  getRooms(): Observable<Room[]> {
    // Simulate an API call with a delay
    return of(this.mockRooms).pipe(delay(500));
  }
}
